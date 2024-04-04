import pytest
from project import log_email_content, get_analysis, validate_config

# dummy config file
# NOTE: THE SYSTEM MESSAGE HAS SINCE BEEN CHANGED IN THE MAIN PROGRAM TO INCLUDE CRYPTO EMAILS, CHANGING THE OUTCOME OF THE ANALYSE_EMAIL FUNCTION WITH THE CURRENT PARAMETERS & TEST FILES
class DummyConfig:
    def __init__(self, **kwargs):
        self.apiKey = kwargs.get('apiKey', "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")
        self.serverName = kwargs.get('serverName', "posteo.de")
        self.email = kwargs.get('email', "jay.e@posteo.net")
        self.port = kwargs.get('port', "993")
        self.maxEmails = kwargs.get('maxEmails', 20)
        self.spamFolder = kwargs.get('spamFolder', "Junk")
        self.searchFolder = kwargs.get('searchFolder', "Notes")
        self.system = kwargs.get('system', "You carefully categorise emails into Spam or Not Spam, and very succinctly explain why.  Only categorise as spam if likelihood is high.  Strictly format your responses: Start with a respective '-Not spam' or '-Spam', followed by a line break, thence 'Reasoning: [your reasoning]'.")
        self.model = kwargs.get('model', "gpt-3.5-turbo")

dummy_config = DummyConfig()

@pytest.mark.parametrize("a, b, c, expected", [
    ("", "JohnSmith@gmail.com", "I forgot to write anything in the body", False),
    ("\r  \n \n", "coldmail@hotmail.com", "ATTN: people who like blank emails", False),
    ("Do you like my email body?", "proficient_emailer@NASA.gov", "I've something to ask...", True),
])

def test_log_email_content(a, b, c, expected):
    _, result = log_email_content(a, b, c)
    assert result == expected

def read_file(file_path):
    with open(file_path, 'r') as file:
        return file.read()


test_files = ['not_spam_1.pld',
              'not_spam_2.pld',
              'not_spam_3.pld',
              'spam_1.pld',
              'spam_2.pld',
              'spam_3.pld']

def test_validate_config():
    config = DummyConfig()
    config.apiKey = "sk-cQ0mx3Uq5Kg6yuSgn4v0RT3BlbEwsfayZeKK9S63kSJPgwaB"
    config.serverName = "server.mcgee.net"
    config.email = "fred_savage2024@yahoo.zh"
    config.port = "993"
    config.maxEmails = 1000
    config.spamFolder = "Spambo2000"
    config.searchFolder = "Zootopia"
    config.system = "Any message here is fine"
    config.model = "also here."
    assert validate_config(config) == True

@pytest.mark.parametrize("apiKey, expected", [
    ("some-random-string123987124", False),
    ("sk-1234567890123456789012345678901234567890123456784", False),
    ("psk-12345678901234567890123456789012345678901234567", False),
    ])

def test_validate_config_apiKey(apiKey, expected):
    config = DummyConfig(apiKey = apiKey)
    assert validate_config(config) == expected


@pytest.mark.parametrize("serverName, expected", [
    ("fred.savage.org", True),
    ("terrible choice", False),
    ("fred.224.org", True),
    ("trailing.dot.com.", False),
    ("imap.mail.me.org", True),
    ("doubledot..com", False),
])

def test_validate_config_servername(serverName, expected):
    config = DummyConfig(serverName = serverName)
    assert validate_config(config) == expected


@pytest.mark.parametrize("email, expected", [
    ("hi_mum@home", False),
    ("terrible choice", False),
    ("forgottheatsymbol.net.com", False),
    ("fred.224.org@schwan.ch", True),
    ("______@underscore.co.jp", True),
    ("doubledot..com", False),
    ("ABC.123@example.net", True),
    ("double@at@symbol", False),
])

def test_validate_config_email(email, expected):
    config = DummyConfig(email = email)
    assert validate_config(config) == expected


@pytest.mark.parametrize("port, expected", [
    ("123", False),
    ("143", True)
])

def test_validate_config_port(port, expected):
    config = DummyConfig(port = port)
    assert validate_config(config) == expected


@pytest.mark.parametrize("file_path", test_files)
def test_get_analysis(file_path):
    payload = read_file("./testing/" + file_path)
    result = get_analysis(payload, dummy_config)
    assert result == False if (file_path[:3] == 'not') else True
