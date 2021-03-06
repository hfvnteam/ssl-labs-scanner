from requests import get
import json
import time
import csv
import sys
import argparse

__author__ = 'K. Coddington'
# https://github.com/ssllabs/ssllabs-scan/blob/stable/ssllabs-api-docs.md


def setargs():
    description = 'This script will scan one or several URLs using the Qualys SSL Labs Scan API. Single scan results ' \
                  'will be displayed in stdout, while scanning from a list will output to a CSV.'
    usage = "\n\nssl-labs-scan.py [-ss URL] [-ms URL_LIST -o OUTPUT_CSV]"
    parser = argparse.ArgumentParser(description=description, usage=usage)

    parser.add_argument('-ss', '--single-site',
                        dest='url',
                        help='Scan a single URL')
    parser.add_argument('-ms', '--multi-site',
                        dest='listfile',
                        help='Scan multiple URLs from newline-delimited text file')
    parser.add_argument('-o', '--output',
                        dest='output_csv',
                        default='output.csv',
                        help='<<Requires -ms option to be set>> Sets file that will receive output results. '
                             'Default = output.csv')

    return parser.parse_args()


def ssllab_info():
    api_info_url = 'https://api.ssllabs.com/api/v2/info'
    response = json.loads(get(api_info_url).text)
    return response


def ssllab_scan(url):
    scan_url = 'https://api.ssllabs.com/api/v2/analyze?host=%s&all=on&ignoreMismatch=on&fromCache=on' % url
    response = json.loads(get(scan_url).text)
    return response


def get_protocol(proto, parsed_json):
    proto_dict = {'ssl2': 512, 'ssl3': 768, 'tls10': 769, 'tls11': 770, 'tls12': 771}
    proto_list = parsed_json['endpoints'][0]['details']['protocols']
    result = any(p['id'] == proto_dict[proto] for p in proto_list)
    return result


def get_qualys_grades(parsed_json_text):
    p = parsed_json_text
    grade = p['endpoints'][0]['grade']
    ti_grade = p['endpoints'][0]['gradeTrustIgnored']
    if grade != 'T':
        return grade
    else:
        return "%s(%s)" % (grade, ti_grade)


def get_fallback(parsed_json_text):
    try:
        return parsed_json_text['endpoints'][0]['details']['fallbackScsv']
    except KeyError:
        return 'n/a'


def get_forward_secrecy(parsed_json_text):
    p = parsed_json_text['endpoints'][0]['details']['forwardSecrecy']
    if p < 1:
        return 'False'
    else:
        return 'True'


def get_poodle_ssl(parsed_json_text):
    return parsed_json_text['endpoints'][0]['details']['poodle']


def get_poodle_tls(parsed_json_text):
    p = parsed_json_text['endpoints'][0]['details']['poodleTls']
    if p == 2:
        return 'True'
    elif p == 1:
        return 'False'
    elif p == -1:
        return 'Test failed'
    elif p == -2:
        return 'TLS not supported'
    elif p == -3:
        return 'Inconclusive (Timeout)'


def get_freak(parsed_json_text):
    return parsed_json_text['endpoints'][0]['details']['freak']


def get_logjam(parsed_json_text):
    return parsed_json_text['endpoints'][0]['details']['logjam']


def get_crime(parsed_json_text):
    p = parsed_json_text['endpoints'][0]['details']['compressionMethods']
    if p == 0:
        return 'False'
    else:
        return 'True'


def get_heartbleed(parsed_json_text):
    return parsed_json_text['endpoints'][0]['details']['heartbleed']


def single_site_output(url):
    print("\nScanning %s..." % url)
    p = ssllab_scan(url)
    if p['status'] != 'READY' and p['status'] != 'ERROR':
        print("   Cached results not found. Running new scan. This could take up to 90 seconds to complete.")
    while p['status'] != 'READY' and p['status'] != 'ERROR':
        time.sleep(4)
        p = ssllab_scan(url)  # stated again to refresh response variable
    if p['status'] == 'READY' and p['endpoints'][0]['statusMessage'] != 'Ready':
        print("%s for %s" % (p['endpoints'][0]['statusMessage'], p['host']))
        sys.exit(0)
    if p['status'] == 'ERROR':
        print("%s for %s" % (p['statusMessage'], p['host']))
        sys.exit(0)
    print("\n--------------------------------------------------------------")
    print("  Results for " + p['host'] + ":\n")
    print("  IP Address: %s" % p['endpoints'][0]['ipAddress'])
    print("  Grade: %s\n" % get_qualys_grades(p))
    print("  SSLv2:   %s" % get_protocol('ssl2', p))
    print("  SSLv3:   %s" % get_protocol('ssl3', p))
    print("  TLSv1.0: %s" % get_protocol('tls10', p))
    print("  TLSv1.1: %s" % get_protocol('tls11', p))
    print("  TLSv1.2: %s\n" % get_protocol('tls12', p))
    print("  TLS Fallback SCSV implemented:       %s" % get_fallback(p))
    print("  Uses Forward Secrecy:                %s" % get_forward_secrecy(p))
    print("  Vulnerable to POODLE (SSLv3) attack: %s" % get_poodle_ssl(p))
    print("  Vulnerable to POODLE (TLS) attack:   %s" % get_poodle_tls(p))
    print("  Vulnerable to FREAK attack:          %s" % get_freak(p))
    print("  Vulnerable to Logjam attack:         %s" % get_logjam(p))
    print("  Vulnerable to CRIME attack:          %s" % get_crime(p))
    print("  Vulnerable to Heartbleed attack:     %s" % get_heartbleed(p))
    print("--------------------------------------------------------------\n")


def get_url_list(listfile):
    url_list = []
    with open(listfile, 'r') as inf:
        a = map(str.strip, inf.readlines())
        for line in a:
            url_list.append(line)
    return url_list


def scan_kickoff(url_list):
    # max_scan_count = ssllab_info()['maxAssessments']
    print("\n------------------------------------------------------------")
    for url in url_list:
        if len(url) == 0:
            continue
        while ssllab_info()['currentAssessments'] >= 5:
            print(" *** Concurrent scan limit reached. Waiting for slots to open. ***")
            time.sleep(15)
        print(" Kicking off scan for %s..." % url)
        ssllab_scan(url)
        time.sleep(1)
    while ssllab_info()['currentAssessments'] > 0:
        time.sleep(5)
    print("\n All scans complete.")
    print("------------------------------------------------------------\n")


def get_cached_results(url_list):
    cached_list = []
    for url in url_list:
        time.sleep(1)
        try:
            print("Retrieving results for %s..." % url)
            response = ssllab_scan(url)
            cached_list.append(response)
        except TypeError:
            print("%s could not be successfully scanned and will not be included in output file.")
    return cached_list


def csv_output(inlist, outfile):
    l = get_cached_results(inlist)
    bad_list = []
    print("------------------------------------------------------------")
    print(" Writing results to %s...\n" % outfile)
    with open(outfile, 'wb+') as outf:
        b = csv.writer(outf, dialect='excel', lineterminator='\n')
        b.writerow(['Site', 'IP Address', 'Qualys Grade', 'SSLv2', 'SSLv3', 'TLSv1.0', 'TLSv1.1', 'TLSv1.2',
                    'TLS Fallback SCSV', 'Forward Secrecy', 'POODLE (SSLv3)', 'POODLE (TLS)', 'FREAK', 'Logjam',
                    'CRIME', 'Heartbleed'])  # insert header row
        for p in l:
            if p['status'] == 'READY' and p['endpoints'][0]['statusMessage'] != 'Ready':
                bad_list.append(p)
                continue
            if p['status'] == 'ERROR':
                bad_list.append(p)
                continue
            b.writerow([p['host'], p['endpoints'][0]['ipAddress'], get_qualys_grades(p), get_protocol('ssl2', p),
                        get_protocol('ssl3', p), get_protocol('tls10', p), get_protocol('tls11', p),
                        get_protocol('tls12', p), get_fallback(p), get_forward_secrecy(p), get_poodle_ssl(p),
                        get_poodle_tls(p), get_freak(p), get_logjam(p), get_crime(p), get_heartbleed(p)])
        if bad_list:
            b.writerow([''])
            b.writerow(['Bad URLs:'])
            for bad_url in bad_list:
                if bad_url['status'] == 'READY':
                    b.writerow([bad_url['host'], bad_url['endpoints'][0]['statusMessage']])
                    continue
                if bad_url['status'] == 'ERROR':
                    b.writerow([bad_url['host'], bad_url['statusMessage']])
    print(" Writing to %s complete." % outfile)
    print("------------------------------------------------------------\n\n")


def main():
    args = setargs()
    if not ssllab_info()['engineVersion']:
        print("SSL Labs API is not reachable at this time. Exiting.")
        sys.exit(0)

    if args.url:
        single_site_output(ssllab_scan(args.url))
        sys.exit(0)

    if args.listfile and args.output_csv:
        try:
            with open(args.output_csv, 'wb+'):
                pass
        except IOError:
            print("\n  Output file is currently in use. Please close the file and try again.")
            sys.exit(0)
        url_list = get_url_list(args.listfile)
        scan_kickoff(url_list)
        csv_output(url_list, args.output_csv)
        sys.exit(0)

    if args.url_list and not args.output_csv:
        print("Output file not set. Please use -h for more information.")
        sys.exit(0)

if __name__ == '__main__':
    main()
