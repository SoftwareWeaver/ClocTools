import subprocess
import pprint
import json
import sys
import datetime
import argparse
import xml.etree.ElementTree as ET
from tabulate import tabulate

__version__ = "0.0.11"
IGNORES = [".locs.json",".git",".gitignore",".vscode"]
# ---------------------------------------------
# Build
# ---------------------------------------------

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
    args = ['cloc', '-xml', '-q', '.','--exclude-dir='+",".join(IGNORES)]
    
    print("Processing: %s %s"%( str(hash), str(commitDate) ))

    data = subprocess.check_output(args).decode('utf-8').strip()
    root = ET.fromstring(data)
    result = parse_cloc_xml_result(root)
    return result

def command_build():
    parser = argparse.ArgumentParser(
            prog="count_locs build",
            description="counts lines of code present in each git commit and stores them in a file."
        )

    _args = parser.parse_args(sys.argv[2:])

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
    for _hash in commits:
        git_checkout(_hash)
        commitDate = git_get_commit_date()
        com = cloc_on_commit(_hash, commitDate)
        com.update({
            'hash': _hash
        })

        date_by_hash[_hash] = commitDate
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

    def myconverter(o):
        if isinstance(o, datetime.datetime):
            return o.__str__()

    with open('.locs.json', 'w') as outfile:
        json.dump(dataset, outfile, indent=4, default = myconverter, sort_keys=True)

# ---------------------------------------------
# Eval
# ---------------------------------------------
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
    re = [
        [x[1].strftime("%Y-%m-%d %H:%M")] + x[2:] + [0,0,0, 0]
        for x in lang
    ]

    for idx in range(0, len(re)-1):
        i0 = re[idx]
        i1 = re[idx+1]
        i0[5] = i0[1] - i1[1] # dfcount
        i0[6] = i0[2] - i1[2] # dcode
        i0[7] = i0[3] - i1[3] # dblank
        i0[8] = i0[4] - i1[4] # dcomment

    # special case ... last entry
    item = re[len(re)-1]
    item[5] = item[1] # dfcount
    item[6] = item[2] # dcode
    item[7] = item[3] # dblank
    item[8] = item[4] # dcomment

    return re

def command_eval():
    parser = argparse.ArgumentParser(
        prog="count_locs eval language",
        description="counts lines of code present in each git commit and stores them in a file."
    )

    parser.add_argument(
        'language',
        help='Programming language'
    )

    _args = parser.parse_args(sys.argv[2:])
    with open('.locs.json', 'r') as infile:
        dataset = json.load(infile)

    # Convert datetime
    for _, data in dataset.items():
        for entry in data:
            entry[1] = datetime.datetime.strptime(entry[1], "%Y-%m-%d %H:%M:%S%z")
    
    if not _args.language in dataset:
        print("Language not in dataset.")
        exit(-1)

    print()
    print("LOCS per commit:")
    print(tabulate(tableData(dataset[_args.language]), 
        headers=["timestamp", "fcount", "code", "blank", "comment", "dfcount","dcode", "dblank", "dcomment"],
        tablefmt="github"
    ))

    print()
    print("LOCS per day:")
    reduced = get_newest_commits(dataset[_args.language], "%Y-%m-%d")
    print(tabulate(tableData(reduced), 
        headers=["timestamp", "fcount", "code", "blank", "comment", "dfcount","dcode", "dblank", "dcomment"],
        tablefmt="github"
    ))

# ---------------------------------------------
# main
# ---------------------------------------------
def main():
    parser = argparse.ArgumentParser(
    prog="count_locs",
    description='',
    usage=("count_locs <command> [<args]\n"
            "\n"
            "The following commands are supported:\n"
            "   build   counts lines of code present in each git commit and stores them in a file."
    ))

    parser.add_argument(
        'command',
        help='Subcommand to run'
    )

    parser.add_argument(
        '--version',
        action='version',
        version='%(prog)s {version}'.format(version=__version__)
    )
    args = parser.parse_args(sys.argv[1:2])

    # get reference to this module
    thismodule = sys.modules[__name__]

    if not hasattr(thismodule, "command_"+args.command):
        print('Unrecognized command')
        parser.print_help()
        exit(1)

    # use dispatch pattern to invoke method with same name
    getattr(thismodule,  "command_"+args.command)()
    

if __name__ == "__main__":
    main()
