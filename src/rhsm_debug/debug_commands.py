#
# Copyright (c) 2010 - 2012 Red Hat, Inc.
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
import os
import sys
import shutil
import logging
import tarfile
from datetime import datetime

import subscription_manager.injection as inj
import subscription_manager.managercli as managercli
from rhsm import ourjson as json
from rhsm.config import initConfig

_ = gettext.gettext

cfg = initConfig()

log = logging.getLogger('rhsm-app.' + __name__)

NOT_REGISTERED = _("This system is not yet registered. Try 'subscription-manager register --help' for more information.")

ASSEMBLE_DIR = '/var/spool/rhsm/debug'


class SystemCommand(managercli.CliCommand):

    def __init__(self, name="system",
                 shortdesc=_("Assemble system information as a tar file or directory"),
                 primary=True):
        super(SystemCommand, self).__init__(name, shortdesc, primary)

        self.parser.add_option("--destination", dest="destination",
                               default="/tmp", help=_("the destination location of the result"))
        # default is to build an archive, this skips the archive and clean up,
        # just leaving the directory of debug info for sosreport to report
        self.parser.add_option("--no-archive", action='store_false',
                               default=True, dest="write_archive",
                               help=_("data will be in an uncompressed directory"))

    def _get_usage(self):
        return _("%%prog %s [OPTIONS] ") % self.name

    def _do_command(self):
        consumer = inj.require(inj.IDENTITY)
        if not consumer.is_valid():
            print NOT_REGISTERED
            sys.exit(-1)

        self._debug_info(consumer.uuid,
                         self.cp,
                         cfg_ref=cfg,
                         server_versions=self.server_versions,
                         client_versions=self.client_versions,
                         dest_dir=self.options.destination,
                         write_archive=self.options.write_archive)

    def _debug_info(self, consumer_uuid, cp, cfg_ref,
                    server_versions, client_versions,
                    dest_dir, write_archive):
        debug_info = DebugInfo(consumer_uuid=consumer_uuid,
                               cp=cp,
                               cfg_ref=cfg_ref,
                               server_versions=server_versions,
                               client_versions=client_versions,
                               dest_dir=dest_dir,
                               write_archive=write_archive)

        # FIXME: exception handling
        debug_info.collect()
        debug_info.save()
        debug_info.cleanup()


class DebugInfo(object):
    def __init__(self, consumer_uuid,
                 cp, dest_dir,
                 cfg_ref,
                 server_versions=None,
                 client_versions=None,
                 write_archive=False):
        # TODO: it would be useful if we could
        self.archive_config = DebugInfoArchiveConfig(destination=dest_dir)
        self.archiver = DebugInfoArchiver(archive_config=self.archive_config)

        import pprint
        pprint.pprint(self.archive_config)
        pprint.pprint(self.archive_config.__dict__)

        self.server_versions = server_versions or {}
        self.client_versions = client_versions or {}

        api_info_collector = DebugInfoApiCollector(consumer_uuid, cp, self.archiver)
        dir_info_collector = DebugInfoDirCollector(self.archiver, cfg_ref)
        ver_info_collector = DebugInfoVersionCollector(self.archiver,
                                                       server_versions,
                                                       client_versions)

        collectors = [api_info_collector,
                      dir_info_collector,
                      ver_info_collector]

        self.collector = DebugInfoCollector(collectors)

        if write_archive:
            self.writer = DebugInfoTarWriter(self.archive_config)
        else:
            self.writer = DebugInfoDirWriter(self.archive_config)

    def collect(self):
        self.collector.collect()

    def save(self):
        self.writer.save()

    def cleanup(self):
        # could add collector cleanup here if needed
        self.archiver.cleanup()
        self.writer.cleanup()


class DebugInfoArchiveConfig(object):
    def __init__(self, destination=None):
        self.assemble_path = ASSEMBLE_DIR
        self.archive_name_slug = "rhsm-system-debug"
        self.archive_name_suffix = self._gen_archive_name_suffix()
        self.archive_name = "%s-%s" % (self.archive_name_slug, self.archive_name_suffix)

        self.tarball_name = "%s.tar.gz" % (self.archive_name)
        self.content_path = os.path.join(self.assemble_path, self.archive_name)
        # /var/spool/rhsm/
        self.tar_path = os.path.join(self.assemble_path, self.tarball_name)
        self.destination = destination
        self.destination_file = os.path.join(self.destination, self.archive_name)

    def _gen_archive_name_suffix(self):
        return datetime.now().strftime("%Y%m%d-%f")


class ConsumerDebugInfo(object):
    def __init__(self,
                 owner=None,
                 subscriptions=None,
                 consumer=None,
                 entitlements=None,
                 pools=None):
        self.owner = owner
        self.subscriptions = subscriptions
        self.consumer = consumer
        self.entitlements = entitlements,
        self.pools = pools


class DebugInfoApiCollector(object):
    def __init__(self, consumer_uuid, cp, archiver):
        self.uuid = consumer_uuid
        self.cp = cp
        self.archiver = archiver

        self.data = ConsumerDebugInfo()

    def gather(self):
        owner = self.cp.getOwner(self.uuid)
        self.data.owner = owner

        try:
            self.data.subscriptions = self.cp.getSubscriptionList(owner['key'])
        except Exception:   # FIXME
            log.warning("Server does not allow retrieval of subscriptions by owner.")

        self.data.consumer = self.cp.getConsumer(self.uuid)
        self.data.compliance = self.cp.getCompliance(self.uuid)
        self.data.entitlements = self.cp.getEntitlementList(self.uuid)
        # FIXME: add keyswords for these args
        self.data.pools = self.cp.getPoolsList(self.uuid, True, None, owner['key'])

    def add_to_archive(self):
        self.add_json("owner", self.data.owner)
        self.add_json("subscriptions", self.data.subscriptions)
        self.add_json("consumer", self.data.consumer)
        self.add_json("entitlements", self.data.entitlements)
        self.add_json("pools", self.data.pools)

    def add_json(self, name, data):
        self.archiver.add_json(name, data)


class DebugInfoDirCollector(object):
    def __init__(self, archiver, cfg):
        self.archiver = archiver
        self.cfg = cfg

        self.dirs = ["/etc/rhsm",
                     "/var/log/rhsm",
                     "/var/lib/rhsm",
                     cfg.get('rhsm', 'productCertDir'),
                     cfg.get('rhsm', 'entitlementCertDir'),
                     cfg.get('rhsm', 'consumerCertDir')]

    def gather(self):
        pass

    def add_to_archive(self):
        for dir_path in self.dirs:
            self.add_dir(dir_path)

    def add_dir(self, dir_path):
        self.archiver.add_dir(dir_path)


class DebugInfoVersionCollector(object):
    def __init__(self, archiver, server_versions, client_versions):
        self.archiver = archiver
        self.server_versions = server_versions
        self.client_versions = client_versions

    def gather(self):
        self.version_info = self._get_version_info()

    def _get_version_info(self):
        return {"server type": self.server_versions["server-type"],
                "subscription management server": self.server_versions["candlepin"],
                "subscription-manager": self.client_versions["subscription-manager"],
                "python-rhsm": self.client_versions["python-rhsm"]}

    def add_to_archive(self):
        self.add_json("version", self.version_info)

    def add_json(self, name, data):
        self.archiver.add_json(name, data)


class DebugInfoCollector(object):
    def __init__(self, collectors=None):
        self.collectors = collectors or []

    def collect(self):
        for collector in self.collectors:
            collector.gather()

        for collector in self.collectors:
            collector.add_to_archive()

    def add_json(self, name, data):
        self.archiver.add_json(name, data)


class SaferFileCopy(object):
    def move(self, src, dst):
        self.copy(src, dst)
        os.unlink(src)

    def copy(self, src, dst):
        pass
        # open src, open dst O_EXCL
        # base on shutil.copyfile/copyfileobj


class DebugInfoTarWriter(object):
    def __init__(self, archive_config):
        self.config = archive_config

    def save(self):
        try:
            tf = tarfile.open(self.config.tar_path, "w:gz")
            tf.add(self.config.content_path)
        finally:
            tf.close()
            # FIXME: full name

        # hmm, dest comes from?
        self._move(self.config.destination_file)

    def _move(self, dest_path):
        # FIXME: move securely
        # FIXME: perms should be 0600, only root can read
        # Okay if the dst dir is someplace we can create a file "securely"
        #   (without a less priv user/group potentially racing us to the
        #   filename), but if say, /tmp, we create the file using mkstemp

        # If we are just writing a file, we can try it O_EXCL and copy the
        # contents
        shutil.move(self.config.tar_path, dest_path)
        print _("Wrote: %s") % dest_path


class DebugInfoDirWriter(object):
    def __init__(self, archive_config):
        self.config = archive_config

    def save(self):
        self._move()

    def _move(self):
        # FIXME: need to do this securely
        shutil.move(self.config.content_path, self.options.destination)

        print _("Wrote: %s/%s") % (self.config.destination,
                                   self.config.destination_file)


class DebugInfoArchiver(object):

    def __init__(self, archive_config):
        self.config = archive_config

        os.makedirs(self.config.content_path)

    def add_json(self, name, json_blob):
        self._write_flat_file(self.config.content_path,
                              "%s.json" % name,
                              json_blob)

    def add_dir(self, dir_path):
        self._copy_directory(dir_path, self.config.content_path)

    def cleanup(self):
        pass
        #FIXME: handle errors
        #os.unlink(self.config.content_path)
#        os.unlink(self.config.tar_path)

    def _write_flat_file(self, content_path, filename, content):
        path = os.path.join(content_path, filename)
        with open(path, "w+") as fo:
            fo.write(json.dumps(content, indent=4, sort_keys=True))

    def _copy_directory(self, src_path, dest_path):
        rel_path = src_path
        if os.path.isabs(src_path):
            rel_path = src_path[1:]
        shutil.copytree(src_path, os.path.join(dest_path, rel_path))
