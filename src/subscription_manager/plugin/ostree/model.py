
import re

from subscription_manager.plugin.ostree import repo_file

OSTREE_REPO_CONFIG = "/ostree/repo/config"

REMOTE_SECTION_MATCH = """remote\s+["'](.+)['"]"""


class OstreeRemote(object):
    """Represents a [remote] entry in /ostree/repo/config"""
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
        """Create a OstreeRemote from a rhsm.certificate.Content."""
        remote = cls()
        remote.name = content.label
        remote.url = content.url

        # ?


class OstreeRemotes(object):
    """All of the [remote] sections in /ostree/repo/config.

    Unknown: If order matters
             If dupes are allowed
             If there is any other nesting (if multiple repo/configs, do
                we care which one they came from."""
    def __init__(self):
        # FIXME: are remotes a set or a list?
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


class OstreeRemoteUpdater(object):
    """Update the config for a ostree repo remote.

    Given a OstreeRemote, update it's model.

    UNUSED atm
    """
    def __init__(self, report):
        self.report = report

    def update(self, remote):
        # replace old one with new one
        pass


class OstreeRemotesUpdater(object):
    """Update ostree_remotes with new remotes.

    Create, replace, update, (delete?) entries from a
    OsteeRemotes.

    Unknown: equality of two OstreeRemote's
             how a remote could obsolete another
             if we need to detect if remotes are the same
                (not an update)
             If any version or other comparison applies
             if remotes need to be updated one by one, or
              can the whole set be replaced at once.
             Is there a difference between updating and replacing?
             How do we detect deletion
    """
    def __init__(self, ostree_remotes, report=None):
        self.report = report
        self.ostree_remotes = ostree_remotes

    def update(self, remotes_set):
        # Just replaces all of the current remotes with the computed remotes.
        # TODO: if we need to support merging, we can't just replace the set,
        #       Would need to have a merge that updates a OstreeRemote one at a
        #       time.
        # Or a subclass could provide a more detailed update
        self.ostree_remotes = remotes_set

        # TODO: update report


class OstreeRepo(object):
    pass


class OstreeRefspec(object):
    """The refspec from a .origin file."""
    pass


class OstreeOrigin(object):
    """The info reprenting a Origin.

    Unknown: Where does the $sha in $sha.origin come from?
             Is $sha->refspec always 1:1?
             Presumably $sha.origin are uniq.
    """
    pass


# whatever is in config:[core]
class OstreeCore(object):
    """Represent /ostree/repo/config [core] section

    Unknown: what any of this info means, and if
             we need to know or or update it."""
    pass


class OstreeConfigRepoConfigFileLoader(object):
    """Load the specific OSTREE_REPO_CONFIG repo config file.

    Create a OstreeCore, OstreeRemotes with values from the config file."""
    repo_config_file = OSTREE_REPO_CONFIG

    def __init__(self, repo_config_file=None):
        if repo_config_file:
            self.repo_config_file = repo_config_file
        self.remotes = None
        self.core = None

    def load(self):
        # raises ConfigParser.Error based exceptions if there is no config or
        # errors reading it.
        # TODO: when/where do we create it the first time?
        self.repo_config = repo_file.RepoFile(self.repo_config_file)
        self.load_remotes()
        self.load_core()

    def load_remotes(self):
        self.remotes = OstreeRemotes.from_config(self.repo_config)

    def load_core(self):
        self.core = OstreeCore()
        self.core.repo_version = self.repo_config.config_parser.get('core', 'repo_version')
        self.core.mode = self.repo_config.config_parser.get('core', 'mode')


class OstreeConfigUpdates(object):
    """The info a ostree update action needs to update OstreeConfig.

    remote sets, origin, refspec, branches, etc.

        All of the info about a repo config that needs to be
        updated. Likely core doesn't change.
    """
    def __init__(self, core=None, remote_set=None):
        self.core = core
        self.remote_set = remote_set


class OstreeConfigUpdatesBuilder(object):
    """Create a OstreeConfigUpdates.

    Read current config, the Contents from ent certs, do whatever
    we need to do to figure out if there are changes in content.

    The Content and OstreeRemote are not equilivent, though they
    _may_ be 1:1, but that is unknown. So based on the ent certs
    Contents, try to build the list of corresponding OstreeRemotes
    and add it to a OstreeConfigUpdates (as well as a OstreeCore)."""
    def __init__(self, ostree_config, content_set, report=None):
        self.ostree_config = ostree_config
        self.content_set = content_set
        self.report = report

    def build(self):
        """Figure out what the new config should be, and return a OstreeConfigUpdates."""
        # NOTE: Assume 1 content == 1 remote.
        # If that's not valid, this has to do more.
        remote_set = set()
        for content in self.content_set:
            remote = OstreeRemote.from_content(content)
            remote_set.add(remote)

        updates = OstreeConfigUpdates(self.ostree_config.core,
                                      remote_set=remote_set)
        return updates


class OstreeConfig(object):
    """Represent the config state os the ostree app.

    Currently just the list of remotes and the core section.
    TODO: add the OstreeOrigin values
    """
    def __init__(self):
        self.remotes = None
        self.core = None

        self.repo_config_loader = OstreeConfigRepoConfigFileLoader()

    def load(self):
        self.repo_config_loader.load()

        self.remotes = self.repo_config_loader.remotes
        self.core = self.repo_config_loader.core


# still needs origin, etc
class OstreeConfigController(object):
    """Controller for OstreeConfig model."""
    def __init__(self, ostree_config=None, report=None):
        self.ostree_config = ostree_config
        self.report = report

    def update(self, updates):
        """
        Change the OstreeConfig model based on whatever
        rules and logic we have for doing that.

        Currently, that means using a OstreeRemotesUpdater to
        replace OstreeConfig's OstreeRemotes set of OstreeRemote
        with
        """
        remotes_updater = OstreeRemotesUpdater(ostree_remotes=self.ostree_config.remotes,
                                              report=self.report)
        remotes_updater.update(updates.remote_set)

        # update core
        # update origin
