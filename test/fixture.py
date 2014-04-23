import difflib
import pprint
import unittest
import sys
import StringIO

from mock import Mock, NonCallableMock, patch

import stubs
import subscription_manager.injection as inj
from subscription_manager import certdirectory
from subscription_manager import identity

# use instead of the normal pid file based ActionLock
from threading import RLock


class FakeLogger:
    def __init__(self):
        self.expected_msg = ""
        self.msg = None
        self.logged_exception = None

    def debug(self, buf):
        self.msg = buf

    def error(self, buf):
        self.msg = buf

    def exception(self, e):
        self.logged_exception = e

    def set_expected_msg(self, msg):
        self.expected_msg = msg

    def info(self, buf):
        self.msg = buf


class FakeException(Exception):
    def __init__(self, msg=None):
        self.msg = msg

    def __str__(self):
        return repr(self.msg)


class Matcher(object):
    def __init__(self, compare, some_obj):
        self.compare = compare
        self.some_obj = some_obj

    def __eq__(self, other):
        return self.compare(self.some_obj, other)


# if we inject a mock identity, we need to create a mock
# id cert, a mock id cert dir, and a mock identity itself
#  and ideally a helper factory to do it in one step
class MockIdentityDirectory(NonCallableMock):
    def get_default_id_cert(self):
        return self.id_cert

    def find_key_by_cert(self, cert):
        return self.id_key

    def add_id_cert_key_pair_from_bufs(self, key, cert):
        pass

class MockIdentity(NonCallableMock):
    pass

#class MockConsumerIdentityAuth(Mock):

#class MockIdentityCertificate(Mock):


class SubManFixture(unittest.TestCase):
    """
    Can be extended by any subscription manager test case to make
    sure nothing on the actual system is read/touched, and appropriate
    mocks/stubs are in place.
    """
    def setUp(self):

        self.mock_consumer_uuid = "fixture_consumer_uuid"

        self.mock_id_cert = Mock(name="IdentityCertificateMock")
        self.mock_id_cert.x509.subject = {'CN': self.mock_consumer_uuid}
        self.mock_id_cert.x509.alt_name = "consumer name"
        self.mock_id_cert.x509.serial = "123123123"
        #mock_id_cert.getConsumerName.return_value = "fixture_identity_mock_name"
        #mock_id_cert.getSerialNumber

        # let's try using a mock here
        self.mock_id_dir = MockIdentityDirectory(spec=certdirectory.IdentityDirectory, name='IdentityDirectoryMock')
        self.mock_id_dir.id_cert = self.mock_id_cert
        ##self.id_dir.id_cert.
        self.mock_id_dir.id_key = "SOME KEY"
        inj.provide(inj.ID_DIR, self.mock_id_dir)

        inj.provide(inj.IDENTITY, identity.Identity)

        # mock_id_dir will return our mock id certs
        # regular Identity will check inject ID_DIR, so we shouldn't
        # need to provide a mock identity at all
        # By default mock that we are registered. Individual test cases
        # can override if they are testing disconnected scenario.
        #id_mock = MockIdentity(name='FixtureIdentityMock')
        #id_mock.exists_and_valid = Mock(return_value=True)
        #id_mock.uuid = 'fixture_identity_mock_uuid'
        #id_mock.name = 'fixture_identity_mock_name'


        # Don't really care about date ranges here:
        self.mock_calc = NonCallableMock()
        self.mock_calc.calculate.return_value = None

        inj.provide(inj.PRODUCT_DATE_RANGE_CALCULATOR, self.mock_calc)

        inj.provide(inj.ENTITLEMENT_STATUS_CACHE, stubs.StubEntitlementStatusCache())
        inj.provide(inj.PROD_STATUS_CACHE, stubs.StubProductStatusCache())
        inj.provide(inj.OVERRIDE_STATUS_CACHE, stubs.StubOverrideStatusCache())
        inj.provide(inj.PROFILE_MANAGER, stubs.StubProfileManager())
        # By default set up an empty stub entitlement and product dir.
        # Tests need to modify or create their own but nothing should hit
        # the system.
        self.ent_dir = stubs.StubEntitlementDirectory()
        inj.provide(inj.ENT_DIR, self.ent_dir)
        self.prod_dir = stubs.StubProductDirectory()
        inj.provide(inj.PROD_DIR, self.prod_dir)

        # we currently inject IDENTITY as well as ID_DIR.
        # We probably only need to inject ID_DIR, if it's a mock that returns
        # mock ID

        # Installed products manager needs PROD_DIR injected first
        inj.provide(inj.INSTALLED_PRODUCTS_MANAGER, stubs.StubInstalledProductsManager())

        self.stub_cp_provider = stubs.StubCPProvider()
        self._release_versions = []
        self.stub_cp_provider.content_connection.get_versions = self._get_release_versions

        inj.provide(inj.CP_PROVIDER, self.stub_cp_provider)
        inj.provide(inj.CERT_SORTER, stubs.StubCertSorter())

        # setup and mock the plugin_manager
        plugin_manager_mock = Mock(name='FixturePluginManagerMock')
        inj.provide(inj.PLUGIN_MANAGER, plugin_manager_mock)
        inj.provide(inj.DBUS_IFACE, Mock(name='FixtureDbusIfaceMock'))

        pooltype_cache = Mock()
        inj.provide(inj.POOLTYPE_CACHE, pooltype_cache)
        # don't use file based locks for tests
        inj.provide(inj.ACTION_LOCK, RLock)

        self.stub_facts = stubs.StubFacts()
        inj.provide(inj.FACTS, self.stub_facts)

        self.dbus_patcher = patch('subscription_manager.managercli.CliCommand._request_validity_check')
        self.dbus_patcher.start()

    def tearDown(self):
        self.dbus_patcher.stop()

    def set_consumer_auth_cp(self, consumer_auth_cp):
        cp_provider = inj.require(inj.CP_PROVIDER)
        cp_provider.consumer_auth_cp = consumer_auth_cp

    def get_consumer_cp(self):
        cp_provider = inj.require(inj.CP_PROVIDER)
        consumer_cp = cp_provider.get_consumer_auth_cp()
        return consumer_cp

    # The ContentConnection used for reading release versions from
    # the cdn. The injected one uses this.
    def _get_release_versions(self, listing_path):
        return self._release_versions


    #def _inject_identity(self, identity_to_inject):

    # FIXME: these guys need to make self.id_dir do the right thing as well
    # For changing injection consumer id to one that fails "is_valid"
    def _inject_mock_valid_consumer(self, uuid=None):
        """For changing injected consumer identity to one that passes is_valid()

        Returns the injected identity if it need to be examined.
        """
    #    identity = NonCallableMock(name='ValidIdentityMock')
    #    identity.uuid = uuid or "VALIDCONSUMERUUID"
    #    identity.is_valid = Mock(return_value=True)
    #    inj.provide(inj.IDENTITY, identity)
        if uuid:
            self.mock_consumer_uuid = uuid
        inj_id = inj.require(inj.IDENTITY)
        inj_id.reload()
        return identity

    def _inject_mock_invalid_consumer(self):
        """For chaning injected consumer identity to one that fails is_valid()

        Returns the injected identity if it need to be examined.
        """
        self.mock_consumer_uuid = None
        inj_id = inj.require(inj.IDENTITY)
        inj_id.reload()

    # use our naming convention here to make it clear
    # this is our extension. Note that python 2.7 adds a
    # assertMultilineEquals that assertEqual of strings does
    # automatically
    def assert_string_equals(self, expected_str, actual_str, msg=None):
        if expected_str != actual_str:
            expected_lines = expected_str.splitlines(True)
            actual_lines = actual_str.splitlines(True)
            delta = difflib.unified_diff(expected_lines, actual_lines, "expected", "actual")
            message = ''.join(delta)

            if msg:
                message += " : " + msg

            self.fail("Multi-line strings are unequal:\n" + message)

    def assert_equal_dict(self, expected_dict, actual_dict):
        mismatches = []
        missing_keys = []
        extra = []

        for key in expected_dict:
            if key not in actual_dict:
                missing_keys.append(key)
                continue
            if expected_dict[key] != actual_dict[key]:
                mismatches.append((key, expected_dict[key], actual_dict[key]))

        for key in actual_dict:
            if key not in expected_dict:
                extra.append(key)

        message = ""
        if missing_keys or extra:
            message += "Keys in only one dict: \n"
            if missing_keys:
                for key in missing_keys:
                    message += "actual_dict:  %s\n" % key
            if extra:
                for key in extra:
                    message += "expected_dict: %s\n" % key
        if mismatches:
            message += "Unequal values: \n"
            for info in mismatches:
                message += "%s: %s != %s\n" % info

        # pprint the dicts
        message += "\n"
        message += "expected_dict:\n"
        message += pprint.pformat(expected_dict)
        message += "\n"
        message += "actual_dict:\n"
        message += pprint.pformat(actual_dict)

        if mismatches or missing_keys or extra:
            self.fail(message)

    def assert_items_equals(self, a, b):
        """Assert that two lists contain the same items regardless of order."""
        if sorted(a) != sorted(b):
            self.fail("%s != %s" % (a, b))
        return True


class Capture(object):
    class Tee(object):
        def __init__(self, stream, silent):
            self.buf = StringIO.StringIO()
            self.stream = stream
            self.silent = silent

        def write(self, data):
            self.buf.write(data)
            if not self.silent:
                self.stream.write(data)

        def getvalue(self):
            return self.buf.getvalue()

    def __init__(self, silent=False):
        self.silent = silent

    def __enter__(self):
        self.buffs = (self.Tee(sys.stdout, self.silent), self.Tee(sys.stderr, self.silent))
        self.stdout = sys.stdout
        self.stderr = sys.stderr
        sys.stdout, sys.stderr = self.buffs
        return self

    @property
    def out(self):
        return self.buffs[0].getvalue()

    @property
    def err(self):
        return self.buffs[1].getvalue()

    def __exit__(self, exc_type, exc_value, traceback):
        sys.stdout = self.stdout
        sys.stderr = self.stderr
