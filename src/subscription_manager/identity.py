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
import os

from rhsm.certificate import create_from_pem
from rhsm.config import initConfig
from subscription_manager.certdirectory import Path
from subscription_manager import injection as inj

CFG = initConfig()

log = logging.getLogger('rhsm-app.' + __name__)

# ConsumerIdentity has an IdentityDataSource
# IdentityDataSource can have-a IdentityCertDirectory
# IdentityCertDirectory
# identity.ConsumerIdentity is a ConsumerIdenti
# identity.Identity is _the_ identity
#
# For now, we will inject an identity_dir

# an interface/abc would look like
# Only the bits that set up authentication for the connection
#  need to care what this object is. Otherwise it should be opaque.

class ConsumerIdentityAuth(object):
    """Consumer identity authentication class, passed where consumer identity
    information is needed for authentication."""
    uuid = None
    name = None


# Note this class is not expected to automatically reflect
#  ID_DIR changes. identity.Identity should handle that.
# This is a cert token, created from an id cert. Not an id cert itself.
class IdentityCertConsumerIdentityAuth(object):
    """ConsumerIdentityAuth based on consumer identity certificates."""
    def __init__(self, identity_cert):
        self.identity_cert = identity_cert

    # FIXME: replace with properties
    def getConsumerId(self):
        subject = self.identity_cert.x509.subject
        return subject.get('CN')

    def getConsumerName(self):
        altName = self.identity_cert.x509.alt_name
        return altName.replace("DirName:/CN=", "")

    def getSerialNumber(self):
        return self.identity_cert.x509.serial

    def __str__(self):
        return 'consumer id cert auth: name="%s", uuid=%s' % \
            (self.getConsumerName(),
             self.getConsumerId())


# Identity wraps ConsumerIdentity, and provides info specific
# to subman needs.
#
# ConsumerIdentityAuth is sort of a auth token
# Identity is a wrapper that knows info about the consumer
#
# Identity has a ConsumerIdentityAuth, and knows how to get/reset one
# Identity also has the consumer uuid  (needed for RHSM api)
# Identity also has the consumer name (for UI)
#
#
# atm, Identity.consumer == auth object
#   That may change to say, Identity.auth, on the assumption it could
#   be OAuth token, or a key/pair identifier to a pkcs#11 module

# we inject an Identity. At the moment, this is the only implementation.
# This would be a nice place to have an abstract base class
class Identity(object):
    """Wrapper for sharing consumer identity without constant reloading."""
    def __init__(self):
        self.reload()

    def reload(self):
        """Check for consumer certificate on disk and update our info accordingly."""
        log.debug("Loading consumer info from identity certificates.")
        try:
            self.auth = self._get_consumer_identity_auth()

            # FIXME: replace with properties
            self.name = self.auth.getConsumerName()
            self.uuid = self.auth.getConsumerId()
        # XXX shouldn't catch the global exception here, but that's what
        # existsAndValid did, so this is better.
        except Exception, e:
            # FIXME: can probably remove this exception logging
            log.exception(e)
            log.info("Error reading consumer identity cert")
            self.consumer = None
            self.name = None
            self.uuid = None

    def _get_consumer_identity_auth(self):
        # Populate this instance of Identity with info from ID_DIR
        # (in this particular impl, via a IdentityCertConsumerIdentityAuth
        # created from a certificate2.IdentityCertificate that we load
        # from ID_DIR
        log.debug("_get_consumer_identity_auth")
        id_dir = inj.require(inj.ID_DIR)
        # FIXME: wrap in exceptions, catch IOErrors etc, raise anything else
        id_cert = id_dir.get_default_id_cert()
        log.debug("foo")
        consumer_identity_auth = IdentityCertConsumerIdentityAuth(id_cert)
        log.debug("bar")
        return consumer_identity_auth

    # this name is weird, since Certificate.is_valid actually checks the data
    # and this is a thin wrapper
    def is_valid(self):
        return self.uuid is not None

    # FIXME: ugly names
    # FIXME: the only thing that uses this is the cli 'identity' command.
    def getConsumerName(self):
        return self.name

    def getConsumerId(self):
        return self.uuid

    # FIXME: identity may not be cert based in future
    def getConsumerCert(self):
        return self.auth.identity_cert

    def __str__(self):
        return "<%s, name=%s, uuid=%s, auth=%s>" % \
                (self.__class__.__name__,
                self.name, self.uuid, self.auth)
