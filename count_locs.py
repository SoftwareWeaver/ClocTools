"""
This python script checks out every single commit of a git repo
excecutes cloc on every file and saves the results over the commit date.
"""

import subprocess
import json
import sys
import datetime
import argparse
import xml.etree.ElementTree as ET
from tabulate import tabulate

__version__ = "0.0.11"
IGNORES = [".locs.json", ".git", ".gitignore", ".vscode"]
# ---------------------------------------------
# Build
# ---------------------------------------------


def git_get_symbolic_ref():
    """ Returns the hash of the current active symbolic reference in a git repo
    """
    try:
        args = ['git', 'symbolic-ref', '--short', 'HEAD']
        return subprocess.check_output(
            args,
            stderr=subprocess.DEVNULL
        ).decode('utf-8').strip('\n')
    except subprocess.CalledProcessError:
        return None


def git_get_rev():
    """ Returns the hash of HEAD of a git repo
    """
    args = ['git', 'rev-parse', 'HEAD']

    return subprocess.check_output(
        args
    ).decode('utf-8').strip("\n")


def git_get_rev_list():
    """ Returns a list of hashes sorted by date of the git repository.
    """
    args = ['git', 'rev-list', 'HEAD']
    rev_list = subprocess.check_output(args).decode('utf-8').split("\n")
    rev_list = rev_list[0:len(rev_list)-1]
    return rev_list


def git_checkout(_hash):
    """ Checkout of hash
    """
    args = ['git', 'checkout', '-q', _hash]
    subprocess.check_output(args).decode('utf-8').split("\n")


def git_get_commit_date():
    """ Returns a datetime object containing the date of the commit
    """
    args = ['git', 'log', '-n1', '--pretty=%cI']
    datestring = subprocess.check_output(args).decode('utf-8').strip("\n")
    return datetime.datetime.strptime(datestring, "%Y-%m-%dT%H:%M:%S%z")


def git_no_changes():
    """ Returns true if a git repo has no changes
    """
    # Check if files were modified
    try:
        modified = False
        gdiff_files = ['git', 'diff-files', '--quiet', '--ignore-submodules']
        subprocess.run(gdiff_files, check=True)
    except subprocess.CalledProcessError:
        modified = True

    # Check if files were added
    try:
        added = False
        gdiff_index = ['git', 'diff-index', '--quiet',
                       '--cached', 'HEAD', '--ignore-submodules']
        subprocess.run(gdiff_index, check=True)
    except subprocess.CalledProcessError:
        added = True

    # Check if there are untracked files
    gls_files = ['git', 'ls-files', '-o', '-z', '--exclude-standard']
    out_ls_file = subprocess.check_output(gls_files).decode('utf-8')
    untracked = len(out_ls_file) != 0

    return (not modified) and (not added) and (not untracked)


def parse_cloc_xml_result(root):
    """ Parses the XML results output from cloc and
        converts that into a Python dicitionary.
    """
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


def execute_cloc_and_parse():
    """ Execute cloc and parse its xml output
    """
    args = ['cloc', '-xml', '-q', '.', '--exclude-dir='+",".join(IGNORES)]
    data = subprocess.check_output(args).decode('utf-8').strip()
    root = ET.fromstring(data)
    result = parse_cloc_xml_result(root)
    return result


def git_parse(rev_list):
    """ Checkouts all revisions in rev_list and does the following with them
        1) Gets the date of the commit and converts it to a datetime object.
        2) Execute cloc on each commit and parse its results.
    """
    stats = []
    date_by_hash = dict()
    for _hash in rev_list:
        git_checkout(_hash)
        commit_date = git_get_commit_date()
        print("Processing: %s %s" % (str(_hash), str(commit_date)))
        com = execute_cloc_and_parse()
        com.update({
            'hash': _hash
        })

        date_by_hash[_hash] = commit_date
        stats.append(com)

    return [date_by_hash, stats]


def save_dataset(dataset):
    """ Saves the dataset to json format.
    """
    def date_converter(obj):
        if isinstance(obj, datetime.datetime):
            return obj.__str__()

        return obj

    with open('.locs.json', 'w') as outfile:
        json.dump(dataset, outfile, indent=4,
                  default=date_converter, sort_keys=True)


def command_build():
    """ Called by main in case the command line contains the "build" keyword
    """
    parser = argparse.ArgumentParser(
        prog="count_locs build",
        description="counts lines of code present in each git commit and stores them in a file."
    )

    _args = parser.parse_args(sys.argv[2:])
    if not git_no_changes():
        print("Local changes. Aborting!")
        sys.exit(-1)

    symbol = git_get_symbolic_ref()

    rev = None
    if symbol is None:
        rev = git_get_rev()

    rev_list = git_get_rev_list()

    date_by_hash, stats = git_parse(rev_list)

    if symbol is not None:
        git_checkout(symbol)
    else:
        git_checkout(rev)

    languages = set()
    for i in stats:
        for k, _ in i['languages'].items():
            languages.add(k)

    dataset = {}
    default = {
        'files_count': 0,
        'code': 0,
        'blank': 0,
        'comment': 0
    }
    for lang in languages:
        locs = [[
            i['hash'],
            date_by_hash[i['hash']],
            i['languages'].get(lang, default)['files_count'],
            i['languages'].get(lang, default)['code'],
            i['languages'].get(lang, default)['blank'],
            i['languages'].get(lang, default)['comment']
            ] for i in stats]
        dataset[lang] = locs

    save_dataset(dataset)

# ---------------------------------------------
# Eval
# ---------------------------------------------


def filter_commits(dataset, timestr):
    """ Returns a list of the newest commits from dataset which unique timestr.
    """
    daydict = dict()
    for i in reversed(dataset):  # reverse order to get youngest item first
        date = i[1].strftime(timestr)
        daydict[date] = i

    newest_commits = []
    for _, i in daydict.items():
        newest_commits.append(i)

    newest_commits.sort(key=lambda x: x[1], reverse=True)
    return newest_commits


def create_tabulate_list(lang):
    """ Creates and returns a list of list in were each line has the following content:
        [timestamp, fcount, code, blank, comment, dfcount, dcode, dblank, dcomment]
    """
    tab_list = [
        [x[1].strftime("%Y-%m-%d %H:%M")] + x[2:] + [0, 0, 0, 0]
        for x in lang
    ]

    for idx in range(0, len(tab_list)-1):
        i_0 = tab_list[idx]
        i_1 = tab_list[idx+1]
        i_0[5] = i_0[1] - i_1[1]  # dfcount
        i_0[6] = i_0[2] - i_1[2]  # dcode
        i_0[7] = i_0[3] - i_1[3]  # dblank
        i_0[8] = i_0[4] - i_1[4]  # dcomment

    # special case ... last entry
    item = tab_list[len(tab_list)-1]
    item[5] = item[1]  # dfcount
    item[6] = item[2]  # dcode
    item[7] = item[3]  # dblank
    item[8] = item[4]  # dcomment

    return tab_list


def command_eval():
    """ Called by main in case the command line contains the "eval" keyword
    """
    try:
        with open('.locs.json', 'r') as infile:
            dataset = json.load(infile)
    except IOError:
        print('File .locs.json not accessible.')
        sys.exit(-1)

    # Language list
    langs = []
    for i, _ in dataset.items():
        langs.append(i)

    parser = argparse.ArgumentParser(
        prog="count_locs eval",
        description="evaluate the dataset written by the build command."
    )

    parser.add_argument(
        '--method',
        choices=['commits', 'daily', 'weekly', 'monthly'],
        required=True,
        help='Choose the evaluation method'
    )

    parser.add_argument(
        '--language',
        choices=langs,
        required=True,
        help='Choose the programming language'
    )

    _args = parser.parse_args(sys.argv[2:])

    # Convert datetime since json stores this as strings
    for _, data in dataset.items():
        for entry in data:
            entry[1] = datetime.datetime.strptime(
                entry[1], "%Y-%m-%d %H:%M:%S%z")

    if _args.method == "commits":
        print()
        print("LOCS per commit:")
        print(tabulate(create_tabulate_list(dataset[_args.language]),
                       headers=["timestamp", "fcount", "code", "blank",
                                "comment", "dfcount", "dcode", "dblank", "dcomment"],
                       tablefmt="github"
                       ))
    elif _args.method == "daily":
        print()
        print("LOCS per day:")
        reduced = filter_commits(dataset[_args.language], "%Y-%m-%d")
        print(tabulate(create_tabulate_list(reduced),
                       headers=["timestamp", "fcount", "code", "blank",
                                "comment", "dfcount", "dcode", "dblank", "dcomment"],
                       tablefmt="github"
                       ))
    elif _args.method == "weekly":
        print()
        print("LOCS per week:")
        reduced = filter_commits(dataset[_args.language], "%Y-%W")
        print(tabulate(create_tabulate_list(reduced),
                       headers=["timestamp", "fcount", "code", "blank",
                                "comment", "dfcount", "dcode", "dblank", "dcomment"],
                       tablefmt="github"
                       ))
    elif _args.method == "monthly":
        print()
        print("LOCS per month:")
        reduced = filter_commits(dataset[_args.language], "%Y-%m")
        print(tabulate(create_tabulate_list(reduced),
                       headers=["timestamp", "fcount", "code", "blank",
                                "comment", "dfcount", "dcode", "dblank", "dcomment"],
                       tablefmt="github"
                       ))

# ---------------------------------------------
# main
# ---------------------------------------------


def main():
    """ The main routine
    """
    parser = argparse.ArgumentParser(
        prog="count_locs",
        description='',
        usage=(
            "count_locs <command> [<args]\n"
            "\n"
            "The following commands are supported:\n"
            "  build   counts lines of code present in each git commit and stores them in a file.\n"
            "  eval    evaluate the dataset written by the build command."
        )
    )

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
        sys.exit(-1)

    # use dispatch pattern to invoke method with same name
    getattr(thismodule, "command_"+args.command)()


if __name__ == "__main__":
    main()
