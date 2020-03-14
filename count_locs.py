import subprocess
import pprint
import json
import datetime
import xml.etree.ElementTree as ET
from tabulate import tabulate

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

def git_no_changes():
    # Check if files were modified
    gdiff_files=['git','diff-files','--quiet','--ignore-submodules']
    modified = subprocess.run(gdiff_files).returncode == 1

    # Check if files were added
    gdiff_index=['git','diff-index','--quiet','--cached', 'HEAD', '--ignore-submodules']
    added = subprocess.run(gdiff_index).returncode == 1

    # Check if there are untracked files
    gls_files=['git','ls-files','-o','-z', '--exclude-standard']
    out_ls_file = subprocess.check_output(gls_files).decode('utf-8')
    untracked = len(out_ls_file) != 0

    return (not modified) and (not added) and (not untracked)

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
    
    print("Processing: %s %s"%( str(hash), str(commitDate) ))

    data = subprocess.check_output(args).decode('utf-8').strip()
    root = ET.fromstring(data)
    result = parse_cloc_xml_result(root)
    return result

def get_newest_commits(dataset, timestr):
    daydict = dict()
    for i in reversed(dataset): # reverse order to get youngest item first
        date = i[1].strftime(timestr)
        daydict[date] = i

    re = []
    for _ , i in daydict.items():
        re.append(i)

    re.sort(key=lambda x:x[1],reverse=True)
    return re

def tableData(lang):
    return [
        [x[1].strftime("%Y-%m-%d %H:%M")] + x[2:]
        for x in lang
    ]

def main():

    if (not git_no_changes()):
        print("Local changes. Aborting!")
        exit(-1)
    
    symbol = git_get_symbolic_ref()
    
    rev = None
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

    print()
    print(tabulate(tableData(dataset['Swift']), 
        headers=["timestamp", "files_count", "code", "blank", "comment"],
        tablefmt="github"
    ))

    print()
    reduced = get_newest_commits(dataset['Swift'], "%Y-%m-%d")
    print(tabulate(tableData(reduced), 
        headers=["timestamp", "files_count","code","blank","comment"],
        tablefmt="github"
    ))

if __name__ == "__main__":
    main()
