import subprocess
import pprint
import json
import xml.etree.ElementTree as ET

def parse_cloc_result(root):

    header = {}

    for item in root.find('header'):
        header[item.tag] = item.text
    
    header['elapsed_seconds'] = float(header['elapsed_seconds'])
    header['files_per_second'] = float(header['files_per_second'])
    header['lines_per_second'] = float(header['lines_per_second'])

    header['n_files'] = int(header['n_files'])
    header['n_lines'] = int(header['n_lines'])
    
    languages = {}
    for item in root.iter('language'):
        attribs = item.attrib
        languages[attribs['name']] = {
            'files_count' : int(attribs['files_count']),
            'blank' : int(attribs['blank']),
            'comment' : int(attribs['comment']),
            'code' : int(attribs['code'])
        }

    
    data={
        'header' : header,
        'languages' : languages
    }
    return data

def cloc_on_commit(hash):
    git_checkout(hash)
    args=['cloc','-xml','-q','.']
    print(args)
    data = subprocess.check_output(args).decode('utf-8').strip()
    root = ET.fromstring(data)
    return parse_cloc_result(root)

def git_checkout(hash):
    args=['git','checkout','-q', hash]
    subprocess.check_output(args).decode('utf-8').split("\n")

def main():
    args=['git','rev-parse', 'HEAD']

    initialCommit = subprocess.check_output(args).decode('utf-8').split("\n")[0]


    args=['git','rev-list', 'HEAD']
    commits = subprocess.check_output(args).decode('utf-8').split("\n")
    commits = commits[0:len(commits)-1]

    stats = []
    for i in commits:
        com = cloc_on_commit(i)
        com.update({
            'hash' : i
        })
        stats.append(com)
    git_checkout(initialCommit)
    swift_loc = [
        [
            i['hash'], 
            i['languages']['Swift']['files_count'], 
            i['languages']['Swift']['code'], 
            i['languages']['Swift']['blank'], 
            i['languages']['Swift']['comment']
        ] for i in stats
    ]
    
    pprint.pprint(swift_loc)
    
    
if __name__ == "__main__":
    main()