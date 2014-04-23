#
# Copyright (c) 2013 Red Hat, Inc.
#
# This software is licensed to you under the GNU General Public License,
# version 2 (GPLv2). There is NO WARRANTY for this software, express or
# implied, including the implied warranties of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. You should have received a copy of GPLv2
# along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.
#
# Red Hat trademarks are not licensed under GPLv2. No permission is
# granted to use or replicate Red Hat trademarks that are incorporated
# in this software or its documentation.
#

import logging


from subscription_manager import certlib
from subscription_manager import injection as inj

log = logging.getLogger('rhsm-app.' + __name__)


class IdentityCertLib(certlib.DataLib):
    """
    An object to update the identity certificate in the event the server
    deems it is about to expire. This is done to prevent the identity
    certificate from expiring thus disallowing connection to the server
    for updates.
    """

    def _do_update(self):
        action = IdentityUpdateAction()
        return action.perform()


class IdentityUpdateAction(object):
    """UpdateAction for consumer identity certificates.

    Returns a certlib.ActionReport. report.status of
    1 indicates identity cert was updated."""
    def __init__(self):
        self.cp_provider = inj.require(inj.CP_PROVIDER)
        self.uep = self.cp_provider.get_consumer_auth_cp()

        # Use the default report
        self.report = certlib.ActionReport()

    def perform(self):
        identity = inj.require(inj.IDENTITY)

        if not identity.is_valid():
            # we could in theory try to update the id in the
            # case of it being bogus/corrupted, ala #844069,
            # but that seems unneeded
            # FIXME: more details
            self.report._status = 0
            return self.report

        return self._update_cert(identity)

    def _update_cert(self, identity):

        consumer_identity = inj.require(inj.IDENTITY)
        # fetch the latest consumer info, include cert
        consumer_info = self._get_consumer(consumer_identity)

        # We want to compare the existing identity info with that fetched from
        # the server. Would like to be able to compare the Consumer json
        # model's id info with the IDENTITY model.
        # only write the cert if the serial has changed

        # aiee
        new_consumer_auth = identity.IdentityCertConsumerIdentityAuth.from_consumer_info(consumer_info)
        log.debug("new consumer auth %s" % new_consumer_auth)

        id_cert = consumer_identity.auth.identity_cert
        if id_cert.getSerialNumber() != consumer_info['idCert']['serial']['serial']:
            log.debug('identity certificate changed, writing new one')

            # add persist and refresh
            consumer_identity.update(consumer_info)
            #id_dir.add_id_cert_key_pair_from_bufs(consumer_info['idCert']['key'],
            #                                      consumer_info['idCert']['cert'])

        # FIXME: use different status to indicate a new id cert
        # updated the cert, or at least checked
        self.report._status = 1
        return self.report

    def _get_consumer(self, identity):
        # FIXME: not much for error handling here
        #
        # If the cp supports it, we could specify a filter here to get
        # just the cert info
        consumer = self.uep.getConsumer(identity.uuid)
        return consumer
