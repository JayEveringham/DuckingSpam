import os
import re
import sys
import json
import socket
import imaplib
import getpass
import argparse
import mailparser
from openai import OpenAI


def parse_arguments():
    """
    Parses command-line arguments

    Returns:
        argparse.Namespace object containing all arguments

    """
    parser = argparse.ArgumentParser(description="AI powered spam detector")
    parser.add_argument("-m", "--move-flagged-mail", action="store_true",
                        help="Move mail flagged as spam from searchFolder to spamFolder (config.json)")
    parser.add_argument("-s", "--save-local-copy", action="store_true",
                        help="Save a local copy of all parsed mail")

    # TESTING ONLY
    # parser.add_argument("-pl", "--save-payload", action="store_true",
    #                     help="Save a local copy of all data (.eml) files along with text (.pld) payloads passed to API")
    # parser.add_argument("-p", "--use-env-password", action="store_true",
    #                     help="Use environment variable for password (set via CLI)")
    return parser.parse_args()


class Decoration:
    """Class used for text decoration of terminal output"""
    RED = '\033[31m'
    BLUE = '\033[34m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    RESET = '\033[0m'  # Reset to default terminal color
    INFO = f"[{BLUE}i{RESET}]"
    TICK = f"[{GREEN}✓{RESET}]"
    CROSS = f"[{RED}X{RESET}]"

    @staticmethod
    def red(text):
        return f'{Decoration.RED}{text}{Decoration.RESET}'

    @staticmethod
    def green(text):
        return f'{Decoration.GREEN}{text}{Decoration.RESET}'

    @staticmethod
    def yellow(text):
        return f'{Decoration.YELLOW}{text}{Decoration.RESET}'

    @staticmethod
    def blue(text):
        return f'{Decoration.BLUE}{text}{Decoration.RESET}'


class Config:
    """Handles loading of config.json and manual input from the user should the file or values not exist. It can also save this data back to file."""
    def __init__(self, config_path):
        self.config_path = config_path
        self.required_keys = ["apiKey", "email", "spamFolder", "searchFolder", "port", "serverName", "maxEmails", "model", "system"]
        self.load_config(config_path)

    def load_config(self, config_path):
        is_missing_config = False
        try:
            with open(self.config_path, 'r') as config_file:
                config_json = json.load(config_file)
        except FileNotFoundError:
            proceed = input(f'{Decoration.blue(self.config_path)} not found. Would you like to proceed? [y/n] ')
            if proceed == 'y':
                config_json = {}
            else:
                sys.exit()

        for key in self.required_keys:
            if key not in config_json or not config_json[key]:
                is_missing_config = True
                user_value = input(f"Config file missing {Decoration.blue(key)}.  Enter value: ")
                config_json[key] = user_value

        if is_missing_config:
            save_query = input(f'Would you like to save this to config? {Decoration.blue("(y/n)")}: ')
            if save_query == "y":
                with open(config_path, 'w') as config_file:
                    json.dump(config_json, config_file, indent=4)
                    print(Decoration.TICK + f" Saved config data to {config_path}")
        else:
            print(Decoration.TICK + " Config loaded")
        for key, value in config_json.items():
            setattr(self, key, value)


def validate_config(config):
    """
    Validates the configuration object against multiple regex patterns. Exits on failure of critical configuration data

    Args:
    config(Config): Config object

    Returns:
    bool: True if config validated, else False.

    """
    valid = True
    try:
        if not re.fullmatch(r'^sk-[a-zA-Z0-9]{48}$', config.apiKey):
            print(f'{Decoration.CROSS} Check configuration: OpenAI API key possiby invalid')
            valid = False
        if not re.fullmatch(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', config.email):
            print(f'{Decoration.CROSS} Check configuration: Email address possibly invalid')
            valid = False
        if not (re.fullmatch(r'^[^\/\\]+$', config.spamFolder) and re.fullmatch(r'^[^\/\\]+$', config.searchFolder)):
            print(f'{Decoration.CROSS} Check configuration: Email folder name/s possibly invalid')
            valid = False
        if not re.fullmatch(r'^(143|993)$', config.port):
            print(f'{Decoration.CROSS} Check configuration: not an IMAP port')
            valid = False
        if not re.fullmatch(r'^(?!-)[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$', config.serverName):
            print(f'{Decoration.CROSS} Check configuration: possibly not a valid server name')
            valid = False
        if config.maxEmails < 1:
            print(f'{Decoration.CROSS} Check configuration: max Email count below 1.  Exiting...')
            sys.exit(1)
        if not re.fullmatch(r'^(?!-)[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$', config.serverName):
            print(f'{Decoration.CROSS} Check configuration: possibly not a valid server name')
            valid = False
        if not re.fullmatch(r'^(?!-)[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$', config.serverName):
            print(f'{Decoration.CROSS} Check configuration: possibly not a valid server name')
            valid = False
        if not config.model:
            print(f'{Decoration.CROSS} Check configuration: need to specify GPT model')
            valid = False
        if not config.system:
            print(f'{Decoration.CROSS} Check configuration: need to specify GPT system instructions')
            valid = False
    except TypeError as e:
        print(f'{Decoration.CROSS} Check configuration data for correct format!\n{Decoration.INFO} {e}\n{Decoration.INFO}Exiting...')
        sys.exit(1)
    return valid


def get_password(email):
    """User input of password"""
    # FOR TESTING ONLY
    # env_pw_name = 'PROJECT'
    # if args.use_env_password and os.getenv(env_pw_name):
    #     password = os.getenv(env_pw_name)
    #     print(f'{Decoration.INFO} Password for {Decoration.blue(str(email))} loaded from environment variable')
    #     return password
    # elif args.use_env_password:
    #     print(f'{Decoration.CROSS} Password not found as environment variable.  Set with {Decoration.blue(f"export {env_pw_name}=password (in single quotes)")}')

    password = getpass.getpass(f"Please enter password for {Decoration.blue(str(email))}: ")
    return password


def get_mail_object(config, password):
    """Logs the user in to email server, returning IMAP object"""
    print(f'{Decoration.INFO} Logging in..', end='', flush=True)
    try:
        mail = imaplib.IMAP4_SSL(host=config.serverName, port=config.port, timeout=15)
        mail.login(config.email, password)
        print(f'\r{Decoration.TICK} Logged in as {Decoration.blue(str(config.email))}')
        return mail
    except socket.gaierror as e:
        if e.errno == -2:
            print(f'\r{Decoration.CROSS} Network error: Unable to reach {Decoration.blue(config.serverName)}.  Please check the server name and network connection\n')
        else:
            print(f'\r{Decoration.CROSS} Network error\n{str(e)}')
    except imaplib.IMAP4.error as e:
        if 'authentication failed' in str(e).lower():
            print(f'\r{Decoration.CROSS} Authentication failed.  Please check username and password\n{str(e)}')
        else:
            print(f'\r{Decoration.CROSS} An IMAP error occured: {str(e)}')
    except OSError as e:
        if e.errno == 101:
            print(f'\r{Decoration.CROSS} Network error: unreachable.  Check your connection and config.json (port number?) and try again.')
        else:
            print(f'\r{Decoration.CROSS} An OS error occured: {str(e)}')
    except Exception as e:
            print(f'\r{Decoration.CROSS} An unexpected error occured: {str(e)}')
    sys.exit(1)


def process_mail(config, mail):
    """Processes email in specified folder, handles iteration over emails, calling of parse and analysis functions, and actions based on the result thereof"""
    global marked_as_spam_count, deleted_count, copied_count
    try:
        response, _ = mail.select(config.searchFolder)
        if response != 'OK':
            print(f'\r{Decoration.CROSS} Failed to select IMAP folder {Decoration.blue(config.searchFolder)}. Check configuration.\n')
            sys.exit(1)
        status, message_numbers = mail.search(None, 'ALL')
    except imaplib.IMAP4.error as e:
        f'\r{Decoration.CROSS} IMAP error when attempting to select {config.searchFolder} as search folder.  \n{str(e)}\n'
        sys.exit(1)

    if status == 'OK':
        print(f'{Decoration.TICK} Status OK\n{Decoration.INFO} Processing maximum {config.maxEmails} emails in {Decoration.blue(f"{config.searchFolder}")}...\n')
        message_numbers_list = message_numbers[0].split()[:config.maxEmails]
        for num in message_numbers_list:
            print(f'{Decoration.INFO} Fetching email...', end='', flush=True)
            status, data = mail.fetch(num, '(RFC822)')
            if status == 'OK':
                global processed_count
                processed_count +=1

                try:
                    payload = parse_email_data(data[0][1])
                    is_spam = get_analysis(payload, config)
                    marked_as_spam_count += 1 if is_spam else 0

                    if is_spam and args.move_flagged_mail:
                        move_flagged_mail(mail, num, config.spamFolder)
                except ValueError:
                    print(f'{Decoration.yellow("[Body empty: skipping]")}\n\n')


def parse_email_data(data):
    """Parses email data using the mailparser library, saving .eml objects if required.  Additionally checks for emails with empty body's"""
    global saved_count
    msg = mailparser.parse_from_bytes(data)

    # SAVE EMAIL IF CLA -s FLAG EXISTS
    if args.save_local_copy:
        save_local_copy(msg.message_id, "eml", data, 'wb')
        saved_count += 1

    email_subject = msg.subject
    email_from = msg.from_[0][1] if msg.from_ else ""
    email_body = "".join(msg.text_plain) if msg.text_plain else ""

    if not email_body:
        email_body = "".join(msg.text_html) if msg.text_html else ""
    email_summary, body_is_loaded = log_email_content(email_body, email_from, email_subject)
    payload = f'{email_summary}\n{email_body}'

    # # FOR TESTING ONLY
    # if args.save_payload:
    #     save_local_copy(msg.message_id, "pld", payload, 'w')

    if body_is_loaded:
        return payload
    else:
        raise ValueError


def save_local_copy(id, ext, data, mode):
    """Saves a local copy of email (or payload) with specified file ext."""
    test_filename = re.sub(r'[\\/*?:"<>|]', "", id)[:10]
    test_filepath = os.path.join('saved_emails', f'{test_filename}.{ext}')
    os.makedirs(os.path.dirname(test_filepath), exist_ok=True)
    with open(test_filepath, mode) as file:
        file.write(data)
        return 1


def log_email_content(body, sender, subject):
    """Logs parsed email content to terminal"""
    body_is_loaded = False
    if re.sub(r'[\r\n]', '', body).strip() != "":
        body_is_loaded = True
    email_summary = (f'\r{"_" * (len(sender) + 6)}\n'
            f'From: {sender}\n'
            f'Subject: {subject}\n')
    print(email_summary)
    return email_summary, body_is_loaded


def get_analysis(email, config):
    """Sends payload & instructions to OpenAI and categorises the response  Returns a bool"""
    client = OpenAI(api_key=config.apiKey)
    print(f'{Decoration.INFO} Body loaded. Sending API request...', end='', flush=True)
    try:
        response = client.chat.completions.create(
        model="gpt-3.5-turbo-0125",
        response_format={ "type": "text" },
        messages=[
            {"role": "system", "content": config.system},
            {"role": "user", "content": email}
        ]
        )
        analysis = response.choices[0].message.content.strip()
        clear_line()
        if re.match(r'^- ?Not', analysis):
            print(f'\r{Decoration.green(
                analysis)}\n')
            return False
        elif re.match(r'^- ?Spam', analysis):
            print(f'\r{Decoration.red(analysis)}\n')
            return True
        else:
            print(f'{Decoration.INFO} Unexpected response:  Unable to determine classification.\n\n{Decoration.yellow(analysis)}\n\n')
            return False
    except(Exception) as e:
        print(f"An error has occured: {e}\n")
        return None


def log_summary(max, searchFolder, spamFolder):
    """Summary of actions taken"""
    print(f'{"_" * (32 + len(searchFolder) + len(str(max)))}\n'
          f'{Decoration.INFO} Finished processing {Decoration.blue(searchFolder)}: max [{Decoration.green(f"{max}")}]\n'
          f'---[{Decoration.green(f"{processed_count}")}] processed\n'
          f'---[{Decoration.green(f"{saved_count}")}] saved locally\n'
          f'---[{Decoration.green(f"{marked_as_spam_count}")}] flagged as spam\n'
          f'---[{Decoration.green(f"{moved_count}")}] moved from {Decoration.blue(searchFolder)} to {Decoration.blue(spamFolder)}\n')


def move_flagged_mail(mail, num, spamFolder):
    """Marks email flagged as spam for deletion"""
    global moved_count
    copied = deleted = 0
    try:
        # copy to spamFolder
        result, _ = mail.copy(num, spamFolder)
        if result == 'OK':
            copied = 1
            # delete from searchFolder
            mail.store(num, '+FLAGS', '\\Deleted')
            deleted = 1
        else:
            raise Exception
    except Exception as e:
            print(f'{Decoration.CROSS} Could not move email to {Decoration.blue(spamFolder)}. Check configuration.\n\nExiting...\n\n')
            sys.exit(1)
    moved_count += 1
    return


def clear_terminal():
    os.system('cls' if os.name == 'nt' else 'clear')
    clear_line()


def clear_line():
    print(f'\r{" " * 50}\r{Decoration.RESET}', end='')


def expunge(mail, searchFolder):
    """Permanetly removes all messages marked for deletion"""
    print("_" * 27 + f'\n{Decoration.INFO} Cleaning up {Decoration.blue(searchFolder)}')
    try:
        mail.expunge()
        print(f'{Decoration.TICK} Done :)\n')
    except Exception as e:
        print(f'{Decoration.CROSS} Unexpected error: {e}\n')


def main():
    clear_terminal()
    config = Config('config.json')
    validate_config(config)
    password = get_password(config.email)
    mail = get_mail_object(config, password)
    process_mail(config, mail)
    expunge(mail, config.searchFolder) if args.move_flagged_mail else None
    log_summary(config.maxEmails, config.searchFolder, config.spamFolder)
    mail.logout()


if __name__ == "__main__":
    # GLOBALS!
    args = parse_arguments()
    moved_count = marked_as_spam_count = processed_count = saved_count = 0
    main()
