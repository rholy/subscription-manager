#
# Copyright (c) 2010 Red Hat, Inc.
#
# Authors: Jeff Ortel <jortel@redhat.com>
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

import gettext
import logging
import os
import stat

from rhsm.certificate import Key, create_from_file, create_from_pem
from rhsm.config import initConfig
from subscription_manager.injection import require, ENT_DIR

log = logging.getLogger('rhsm-app.' + __name__)

_ = gettext.gettext

cfg = initConfig()

# FIXME: move to rhsm/certficate.
# FIXME: make finer grained, see python-nss nss.error for example
class KeyException(Exception):
    pass


class Directory(object):

    def __init__(self, path):
        self.path = Path.abs(path)

    # FIXME: some path weirdness here. Why does this
    #        not use
    def list_all(self):
        all_items = []
        if not os.path.exists(self.path):
            return all_items

        for fn in os.listdir(self.path):
            p = (self.path, fn)
            all_items.append(p)
        return all_items

    # impl specific matcher for "list"
    def _filename_match(self, filename):
        """Default _filename_match matches all filenames."""
        return True

    def list_files(self):
        files = []
        for p, fn in self.list_all():
            path = self.abspath(fn)
            if Path.isdir(path):
                continue

            if self._filename_match(fn):
                files.append((p, fn))
        return files

    def listdirs(self):
        dirs = []
        for p, fn in self.list_all():
            path = self.abspath(fn)
            if Path.isdir(path):
                dirs.append(Directory(path))
        return dirs

    def create(self):
        if not os.path.exists(self.path):
            os.makedirs(self.path)

    def delete(self):
        self.clean()
        os.rmdir(self.path)

    def clean(self):
        if not os.path.exists(self.path):
            return

        for x in os.listdir(self.path):
            path = self.abspath(x)
            if Path.isdir(path):
                d = Directory(path)
                d.delete()
            else:
                os.unlink(path)

    def abspath(self, filename):
        """
        Return path for a filename relative to this directory.
        """
        # NOTE: self.path is already aware of the Path.ROOT setting, so we
        # can just join normally.
        return os.path.join(self.path, filename)

    def __str__(self):
        return self.path


class CertificateDirectory(Directory):

    KEY = 'key.pem'

    # default expected cert permisions
    CERT_OWNER_UID = 0  # root
    CERT_GROUP_GID = 0
    CERT_PERMS = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP

    def __init__(self, path):
        super(CertificateDirectory, self).__init__(path)
        self.create()
        self._listing = None

    def refresh(self):
        # simply clear the cache. the next list() will reload.
        self._listing = None

    def _filename_match(self, filename):
        if not filename.endswith('.pem') or filename.endswith(self.KEY):
            return False
        return True

    def list(self):
        if self._listing is not None:
            return self._listing
        listing = []
        for p, fn in self.list_files():
            path = self.abspath(fn)
            listing.append(create_from_file(path))
        self._listing = listing
        return listing

    def list_valid(self):
        valid = []
        for c in self.list():
            if c.is_valid():
                valid.append(c)
        return valid

    def list_expired(self):
        expired = []
        for c in self.list():
            if c.is_expired():
                expired.append(c)
        return expired

    def add_cert(self, cert):
        """Add Certificate to directory, persist it, and refresh CertificateDirectory."""
        cert.write()
        log.debug("Added cert %s to %s and saved it" % (cert, self))
        # refresh here or leave that up to caller?
        self.refresh()

    def add_key(self, key):
        "Add Key to directory, persist it, and fresh CertificateDirectory."""
        key.write()
        log.debug("Added key %s to %s and saved it" % (key, self))
        self.refresh()

    def add(self, cert, key):
        "Add Certificate cert, and Key key to CertificateDirectory, persist them, and refresh."""
        self.add_cert(cert)
        self.add_key(key)

    def find(self, sn):
        # TODO: could optimize to just load SERIAL.pem? Maybe not in all cases.
        for c in self.list():
            if c.serial == sn:
                return c
        return None

    # vaguely based on NSS find_key_by_cert
    # TODO: make this more nss'ish, and potentially
    #       handle being able to read certs by not keys
    #       (for, a non root user running this)
    def find_key_by_cert(self, cert):
        """Find the private key for the certificate."""

        # This is cert directory specific, so NotImplemented in
        # CertificateDirectory
        raise NotImplemented

    def _check_cert_perms(self, filename):
        # doesn't exist. We could race between listdir and here.

        # FIXME: ditch entirely, or add a PermFixer we can mock
        if not os.path.exists(filename):
            return

        statinfo = os.stat(filename)

        if statinfo[stat.ST_UID] != self.CERT_OWNER or statinfo[stat.ST_GID] != self.CERT_GROUP:
            #os.chown(filename, self.CERT_OWNER, self.CERT_GROUP)
            log.warn("Detected incorrect ownership of %s." % filename)

        mode = stat.S_IMODE(statinfo[stat.ST_MODE])
        if mode != self.CERT_PERMS:
            #os.chmod(filename, self.CERT_PERMS)
            log.warn("Detected incorrect permissions on %s." % filename)

    # NOTE: Directory.create() currently will create the dir if it
    # doesn't exist
    def check_perms(self):
        for p, fn in self.list_files():
            # if we get here, the dir exists and had something in it.
            # do we need to check existsistence/perms of dir earlier?
            self._check_cert_perms(fn)



# FIXME: product/ent/id dirs do not need to be "directory" based apis
#        The default version of an Entitlements database object would
#        have a CertDirectory, but it doesn't need to be a subclass.
#
#        That would let tests mock out just the Directory objects, and
#        test TheObjectsCurrentlyKnownAsEntitlementDirectory be tested without
#        filesystem access
#
#        The directory based classes could also have a file/dir change
#        notifier, replacing the ones used in cert sorter.
#
#        The Entitlements db object could/would sync itself based on
#        either file change notification (cert dropped in out of band)
#        or explicitily (a refresh() or a init of an object)
#
#
class ProductDirectory(CertificateDirectory):

    PATH = cfg.get('rhsm', 'productCertDir')

    def __init__(self):
        super(ProductDirectory, self).__init__(self.PATH)

    def get_provided_tags(self):
        """
        Iterates all product certificates in the directory and extracts a master
        set of all tags they provide.
        """
        tags = set()
        for prod_cert in self.list_valid():
            for product in prod_cert.products:
                for tag in product.provided_tags:
                    tags.add(tag)
        return tags

    def get_installed_products(self):
        prod_certs = self.list()
        installed_products = {}
        for product_cert in prod_certs:
            product = product_cert.products[0]
            installed_products[product.id] = product_cert
        log.debug("Installed product IDs: %s" % installed_products.keys())
        return installed_products

    def find_by_product(self, p_hash):
        for c in self.list():
            for p in c.products:
                if p.id == p_hash:
                    return c
        return None

    #Set up an alias for backwards compatibility
    findByProduct = find_by_product


class IdentityDirectory(CertificateDirectory):

    PATH = cfg.get('rhsm', 'consumerCertDir')
    CERT_FILENAME = "cert.pem"
    KEY_FILENAME = "key.pem"

    def _filename_match(self, filename):
        if filename == self.CERT_FILENAME:
            return True
        return False

    def find_key_by_cert(self, cert):
        # TODO: atm, there is only one identity, so
        # we just return that key
        # self.path includes ROOT prefix
        key_path = os.path.join(self.path, self.KEY_FILENAME)
        key = Key.read(key_path)
        return key

    def get_default_id_cert(self):
        # TODO: only one id atm
        # TODO: api would need to learn to request a specific consumer uuid
        all_certs = self.list()

        # Only one cert expected
        return all_certs[0]

    def delete_default_id(self):
        id_cert = self.get_default_id_cert()
        key = self.find_key_by_cert(id_cert)

        log.info("Deleting default consumer identity certificate: %s and key: %s." % (id_cert.path, key.path))
        # TODO: likely needs exception handling
        id_cert.delete()
        key.delete()

    def get_id_cert_by_uuid(self, uuid):
        # load all certs, look through them to find matching uuid, return
        # IdentityCert. Maybe useful for virt-who scenarios?
        raise NotImplemented

    def add_id_cert_key_pair_from_bufs(self, cert_buf, key_buf):
        """Create id cert and key, and save them to disk."""
        id_cert = create_from_pem(cert_buf)
        id_key = Key(key_buf)
        self.add(id_cert, id_key)


class EntitlementDirectory(CertificateDirectory):

    PATH = cfg.get('rhsm', 'entitlementCertDir')
    PRODUCT = 'product'

    @classmethod
    def productpath(cls):
        return cls.PATH

    def __init__(self):
        super(EntitlementDirectory, self).__init__(self.productpath())

    def _convert_key_format(self, old_key_path, cert):
        # write the key/cert out again in new style format
        key = Key.read(old_key_path)
        cert_writer = Writer(self)
        cert_writer.write(key, cert)

    # vaguely based on NSS find_key_by_cert
    # TODO: make this more nss'ish, and potentially
    #       handle being able to read certs by not keys
    #       (for, a non root user running this)
    def find_key_by_cert(self, cert):
        """Find the private key for the certificate."""
        # We know the cert path for all of our certs, so we should
        # be able to find the corresponding key for each cert directory
        # type.

        # None path may make sense, but atm we don't know how to
        # look up keys for that in a cert directory
        if cert.path is None:
            return None

        key_path = "%s/%s-key.pem" % (self.path, cert.serial)
        if not os.access(key_path, os.R_OK):
            # read key from old key path
            old_key_path = "%s/key.pem" % self.path

            # if we don't have a new style or old style key, consider the
            # cert invalid
            if not os.access(old_key_path, os.R_OK):
                # Key read/access exceptions could be from Key or it's db
                raise KeyException

            self._convert_key_format(old_key_path, cert)

        # we could either read the key in new format, or we couldn't and we
        # converted it. Read it.

        # FIXME: need ioerror handling likely
        #        and probably KeyReadException style exceptions
        key = Key.read(key_path)
        return key

    def list_valid(self):
        valid = []
        for c in self.list():

            # If something is amiss with the key for this certificate, consider
            # it invalid:
            try:
                self.find_key_for_cert(c)
            except KeyException, e:
                log.exception(e)
                # FIXME: which key, from where, what method, etc
                log.debug("Attempting to read ent cert key, but failed.")
                continue

            if c.is_valid():
                valid.append(c)

        return valid

    def list_for_product(self, product_id):
        """
        Returns all entitlement certificates providing access to the given
        product ID.
        """
        entitlements = []
        for cert in self.list():
            for cert_product in cert.products:
                if product_id == cert_product.id:
                    entitlements.append(cert)
        return entitlements

    def find_all_by_product(self, p_hash):
        certs = set()
        providing_stack_ids = set()
        stack_id_map = {}
        for c in self.list():
            for p in c.products:
                if p.id == p_hash:
                    certs.add(c)
                    # Keep track of stacks that provide our product
                    if (c.order and c.order.stacking_id):
                        providing_stack_ids.add(c.order.stacking_id)

            # Keep track of stack ids in case we need them later.  avoids another loop
            if (c.order and c.order.stacking_id):
                if c.order.stacking_id not in stack_id_map:
                    stack_id_map[c.order.stacking_id] = set()
                stack_id_map[c.order.stacking_id].add(c)

        # Complete
        for stack_id in providing_stack_ids:
            certs |= stack_id_map[stack_id]

        return list(certs)

class Path:

    # Used during Anaconda install by the yum pidplugin to ensure we operate
    # beneath /mnt/sysimage/ instead of /.
    ROOT = '/'

    @classmethod
    def join(cls, a, b):
        path = os.path.join(a, b)
        return cls.abs(path)

    @classmethod
    def abs(cls, path):
        """ Append the ROOT path to the given path. """
        if os.path.isabs(path):
            return os.path.join(cls.ROOT, path[1:])
        else:
            return os.path.join(cls.ROOT, path)

    @classmethod
    def isdir(cls, path):
        return os.path.isdir(path)


class Writer:

    def __init__(self):
        self.ent_dir = require(ENT_DIR)

    def write(self, key, cert):
        serial = cert.serial
        ent_dir_path = self.ent_dir.productpath()

        key_filename = '%s-key.pem' % str(serial)
        key_path = Path.join(ent_dir_path, key_filename)
        key.write(key_path)

        cert_filename = '%s.pem' % str(serial)
        cert_path = Path.join(ent_dir_path, cert_filename)
        cert.write(cert_path)
