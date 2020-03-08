import subprocess
import pprint
import json
import datetime
import xml.etree.ElementTree as ET


def git_get_symbolic_ref():
    try:
        args = ['git', 'symbolic-ref', '--short', 'HEAD']
        return subprocess.check_output(
            args,
            stderr=subprocess.DEVNULL
        ).decode('utf-8').strip('\n')
    except subprocess.CalledProcessError:
        return None


def git_get_rev():
    args = ['git', 'rev-parse', 'HEAD']

    return subprocess.check_output(
        args
    ).decode('utf-8').strip("\n")

def git_checkout(hash):
    args = ['git', 'checkout', '-q', hash]
    subprocess.check_output(args).decode('utf-8').split("\n")

def git_get_commit_date():
    args=['git','log','-n1','--pretty=%cI']
    datestring = subprocess.check_output(args).decode('utf-8').strip("\n")
    return datetime.datetime.strptime(datestring, "%Y-%m-%dT%H:%M:%S%z")

def parse_cloc_xml_result(root):

    header = {}

    for item in root.find('header'):
        header[item.tag] = item.text

    # convert numbers
    header['elapsed_seconds'] = float(header['elapsed_seconds'])
    header['files_per_second'] = float(header['files_per_second'])
    header['lines_per_second'] = float(header['lines_per_second'])

    header['n_files'] = int(header['n_files'])
    header['n_lines'] = int(header['n_lines'])

    languages = {}
    for item in root.iter('language'):
        attribs = item.attrib
        languages[attribs['name']] = {
            'files_count': int(attribs['files_count']),
            'blank': int(attribs['blank']),
            'comment': int(attribs['comment']),
            'code': int(attribs['code'])
        }

    data = {
        'header': header,
        'languages': languages
    }
    return data


def cloc_on_commit(hash, commitDate):
    git_checkout(hash)
    
    args = ['cloc', '-xml', '-q', '.']
    
    print("%s %s"%( str(hash), str(commitDate) ))

    data = subprocess.check_output(args).decode('utf-8').strip()
    root = ET.fromstring(data)
    result = parse_cloc_xml_result(root)
    return result

def main():
    rev = None
    symbol = git_get_symbolic_ref()
    if symbol is None:
        rev = git_get_rev()
        
    args = ['git', 'rev-list', 'HEAD']
    commits = subprocess.check_output(args).decode('utf-8').split("\n")
    commits = commits[0:len(commits)-1]

    stats = []
    date_by_hash = dict()
    for i in commits:
        commitDate = git_get_commit_date()
        com = cloc_on_commit(i, commitDate)
        com.update({
            'hash': i
        })

        date_by_hash[i] = commitDate
        stats.append(com)

    if symbol is not None:
        git_checkout(symbol)
    else:
        git_checkout(rev)

    langs = set()
    for i in stats:
        for k, _ in i['languages'].items():
            langs.add(k)

    dataset = {}
    last = {
        'files_count': 0,
        'code': 0,
        'blank': 0,
        'comment': 0
    }
    for l in langs:
        try:
            locs = [
                [
                    i['hash'],
                    date_by_hash[i['hash']],
                    i['languages'].get(l, last)['files_count'],
                    i['languages'].get(l, last)['code'],
                    i['languages'].get(l, last)['blank'],
                    i['languages'].get(l, last)['comment']
                ] for i in stats
            ]
            dataset[l] = locs
        except:
            continue

    for i in dataset['Swift']:
        print("%s %i %i %i %i"%(i[1], i[2], i[3], i[4], i[5]))


if __name__ == "__main__":
    main()
