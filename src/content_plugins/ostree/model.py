
import re

from content_repos.ostree import repo_file

OSTREE_REPO_CONFIG="/ostree/repo/config"

REMOTE_SECTION_MATCH = """remote\s+["'](.+)['"]"""


class OstreeRemote(object):
    @classmethod
    def from_config_section(cls, section, items):
        remote = cls()
        remote.url = items['url']
        remote.branches = items['branches']
        remote.gpg_verify = items['gpg-verify']
        name = OstreeRemote.name_from_section(section)
        remote.name = name
        return remote

    @staticmethod
    def name_from_section(section):
        """Parse the remote name from the name of the config file section.

        ie, 'remote "awesome-os-7-ostree"' -> "awesome-os-7-ostree".
        """
        matcher = re.compile(REMOTE_SECTION_MATCH)
        result = matcher.match(section)
        if result:
            return result.group(0)

        # FIXME
        raise Exception

    @classmethod
    def from_content(cls, content):
        remote = cls()
        remote.name = content.label
        remote.url = content.url

        # ?

class OstreeRemotes(object):
    def __init__(self):
        self.data = []

    @classmethod
    def from_config(cls, repo_config):
        remotes = cls()
        sections = repo_config.remote_sections()
        for section in sections:
            items = repo_config.items()
            remote = OstreeRemote.from_config_section(section, items)
            remotes.data.append(remote)
        return cls


class OstreeRepo(object):
    pass


class OstreeRefspec(object):
    pass


class OstreeOrigin(object):
    pass


# whatever is in config:[core]
class OstreeCore(object):
    pass

class OstreeConfigRepoConfigFileLoader(object):
    repo_config_file = OSTREE_REPO_CONFIG

    def __init__(self, repo_config_file):
        if repo_config_file:
            self.repo_config_file = repo_config_file
        self.remotes = None
        self.core = None


    def load(self):
        self.repo_config = repo_file.RepoFile(self.repo_config)
        self.load_remotes()
        self.load_core()

    def load_remotes(self):
        self.remotes = OstreeRemotes.from_config(self.repo_config)

    def load_core(self):
        self.core = OstreeCore()
        self.core.repo_version = self.repo_config.get('core', 'repo_version')
        self.core.mode = self.repo_config.get('core', 'mode')


class OstreeConfig(object):
    def __init__(self):
        self.remotes = None
        self.core = None

        self.repo_config_loader = OstreeConfigRepoConfigFileLoader()

    def load(self):
        self.repo_config_loader.load()

        self.remotes = self.repo_config_loader.remotes
        self.core = self.repo_config_loader.core
