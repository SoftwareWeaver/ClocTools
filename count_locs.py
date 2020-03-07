import subprocess
import pprint
import json
import dateutil.parser

def main():
    args=['git','rev-list','--date=iso8601','--pretty=format:{"hash":"%h","date":"%cd"}', 'HEAD']
    output = subprocess.check_output(args).decode('utf-8').split("\n")
    commits = [json.loads(x) for x  in output[1::2]]
    commits = [
        {
            'hash' : x['hash'], 
            'date': dateutil.parser.parse(x['date'])
        } 
        for x in commits
    ]
    
    pprint.pprint(commits)
if __name__ == "__main__":
    main()