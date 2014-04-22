#
# Copyright (c) 2011 Red Hat, Inc.
#
# This software is licensed to you under the GNU General Public
# License as published by the Free Software Foundation; either version
# 2 of the License (GPLv2) or (at your option) any later version.
# There is NO WARRANTY for this software, express or implied,
# including the implied warranties of MERCHANTABILITY,
# NON-INFRINGEMENT, or FITNESS FOR A PARTICULAR PURPOSE. You should
# have received a copy of GPLv2 along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.
#

import mock

import fixture

from subscription_manager import identity
from subscription_manager import identitycertlib
from subscription_manager import injection as inj

CONSUMER_DATA = {'releaseVer': {'id': 1, 'releaseVer': '123123'},
                 'serviceLevel': "Pro Turbo HD Plus Ultra",
                 'owner': {'key': 'admin'},
                 'idCert': {'serial': {'serial': 3787455826750723380},
                            'key': 'CONSUMER_DATA_STUB_PRIVATE_KEY',
                            'cert': 'CONSUMER_DATA_STUB_CERTIFICATE_INFORMATION'}}


mock_consumer_identity = mock.Mock(spec=identity.IdentityCertConsumerIdentityAuth)
mock_consumer_identity.getSerialNumber.return_value = 3787455826750723380
mock_consumer_identity.getConsumerName.return_value = "Mock Consumer Identity"
mock_consumer_identity.getConsumerId.return_value = "11111-00000-11111-0000"


# Identities to inject for testing
class StubIdentity(identity.Identity):
    _consumer = None

    def _get_consumer_identity(self):
        return self._consumer


class InvalidIdentity(StubIdentity):
    pass


class ValidIdentity(StubIdentity):
    _consumer = mock_consumer_identity


different_mock_consumer_identity = mock.Mock(spec=identity.IdentityCertConsumerIdentityAuth)
different_mock_consumer_identity.getSerialNumber.return_value = 123123123123
different_mock_consumer_identity.getConsumerName.return_value = "A Different Mock Consumer Identity"
different_mock_consumer_identity.getConsumerId.return_value = "AAAAAA-BBBBB-CCCCCC-DDDDD"


class DifferentValidConsumerIdentity(StubIdentity):
    _consumer = different_mock_consumer_identity


class TestIdentityUpdateAction(fixture.SubManFixture):

    def setUp(self):
        super(TestIdentityUpdateAction, self).setUp()

        mock_uep = mock.Mock()
        mock_uep.getConsumer.return_value = CONSUMER_DATA

        self.set_consumer_auth_cp(mock_uep)

    def test_idcertlib_persists_cert(self):
        id_update_action = identitycertlib.IdentityUpdateAction()

        mock_valid_id = DifferentValidConsumerIdentity()
        inj.provide(inj.IDENTITY, mock_valid_id)
        id_update_action.perform()

        # there is no cert data in the mocks, so can't look for it
        self.assertTrue(mock_valid_id.write.called)
        self.assertTrue(self.id_dir.add.called)

    def test_idcertlib_noops_when_serialnum_is_same(self):
        id_update_action = identitycertlib.IdentityUpdateAction()
        #certlib.ConsumerIdentity = stubs.StubConsumerIdentity
        #certlib.ConsumerIdentity.getSerialNumber = getSerialNumber

        mock_invalid_id = InvalidIdentity()
        inj.provide(inj.IDENTITY, mock_invalid_id)

        id_update_action.perform()
        self.assertFalse(mock_invalid_id.write.called)

    def test_idcertlib_no_id_cert(self):
        inj.provide(inj.IDENTITY, InvalidIdentity())
        id_update_action = identitycertlib.IdentityUpdateAction()
        report = id_update_action.perform()
        self.assertEquals(report._status, 0)


class TestIdentityCertLib(fixture.SubManFixture):
    def setUp(self):
        super(TestIdentityCertLib, self).setUp()

        mock_uep = mock.Mock()
        mock_uep.getConsumer.return_value = CONSUMER_DATA

        self.set_consumer_auth_cp(mock_uep)

    def test(self):
        id_cert_lib = identitycertlib.IdentityCertLib()
        report = id_cert_lib.update()
        self.assertEquals(report._status, 1)
        self.assertTrue(self.id_dir.add_id_cert_key_pair_from_bufs.called)
