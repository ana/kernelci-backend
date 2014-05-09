# Copyright (C) 2014 Linaro Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Container for all the boot import related functions."""

import glob
import os
import pymongo
import re

from bson import tz_util
from datetime import (
    datetime,
    timedelta
)

from models import DB_NAME
from models.boot import BootDocument
from utils import (
    BASE_PATH,
    LOG,
)
from utils.db import save

BOOT_REPORT_SUFFIX = '-boot-report.log'
# Pattern used for glob matching files on the filesystem.
BOOT_REPORT_PATTERN = '*' + BOOT_REPORT_SUFFIX

RE_TREE_BRANCH = re.compile(r'^Tree/Branch')
RE_GIT_DESCRIBE = re.compile(r'^Git\s{1}describe')
RE_REPORT_SECTION = re.compile(r'^Full\s{1}Report')
RE_DECFONFIG_SECTION = re.compile(r'.*_defconfig$')


def import_and_save_boot(json_obj, base_path=BASE_PATH):
    """Wrapper function to be used as an external task.

    This function should only be called by Celery or other task managers.
    Import and save the boot report as found from the parameters in the
    provided JSON object.

    :param json_obj: The JSON object with the values that identify the boot
        report log.
    :param base_path: The base path where to start looking for the boot log
        file. It defaults to: /var/www/images/kernel-ci.
    """
    database = pymongo.MongoClient()[DB_NAME]

    docs = parse_boot_from_json(json_obj, base_path)

    if docs:
        try:
            save(database, docs)
        finally:
            database.connection.disconnect()
    else:
        LOG.info("No boot log imported")


def parse_boot_from_json(json_obj, base_path=BASE_PATH):
    """Parse boot log file from a JSON object.

    The provided JSON object, a dict-like object, should contain at least the
    `job` and `kernel` keys.

    :param json_obj: A dict-like object that should contain the keys `job` and
    :param base_path: The base path where to start looking for the boot log
        file. It defaults to: /var/www/images/kernel-ci.
    :return A list with all the `BootDocument`s.
    """
    docs = []

    job_dir = json_obj['job']
    kernel_dir = json_obj['kernel']

    boot_log_name = kernel_dir + BOOT_REPORT_SUFFIX
    boot_log = os.path.join(base_path, job_dir, boot_log_name)

    if os.path.isfile(boot_log):
        LOG.info("Parsing boot log for %s - %s", job_dir, kernel_dir)
        docs.extend(_parse_boot_log(boot_log))
    else:
        LOG.warn(
            "Cannot parse boot log for %s - %s: boot report file does "
            "not exists", job_dir, kernel_dir,
        )

    return docs


def _parse_boot_log(boot_log):
    """Parse a boot log file.

    The structure of the file makes so that this function will return a list
    of documents, one for each defconfig found in the boot log file. Each
    document will then contain a list with all the boards.

    :param boot_log: Path to the boot log file. No checks are performed on it.
    :return A list of boot documents.
    """

    LOG.info("Parsing boot log %s", boot_log)

    created = datetime.fromtimestamp(
        os.stat(boot_log).st_mtime, tz=tz_util.utc
    )

    job = None
    kernel = None
    defconfig = None

    report_section = False
    defconf_section = False

    boot_docs = []
    boot_doc = None

    with open(boot_log) as read_boot:
        for line in read_boot:
            line = line.strip()

            if line and not report_section:
                if RE_TREE_BRANCH.match(line):
                    job = line.split(':')[1].strip()
                elif RE_GIT_DESCRIBE.match(line):
                    kernel = line.split(':')[1].strip()
                elif RE_REPORT_SECTION.match(line):
                    report_section = True
            elif report_section:
                if line and not defconf_section:
                    if RE_DECFONFIG_SECTION.match(line):
                        defconfig = line.strip()
                        defconf_section = True

                        doc_id = BootDocument.ID_FORMAT % (
                            {
                                'job': job,
                                'kernel': kernel,
                                'defconfig': defconfig
                            }
                        )
                        boot_doc = BootDocument(doc_id, job, kernel, defconfig)
                        boot_doc.created = created
                        boot_docs.append(boot_doc)
                elif line and defconf_section:
                    if line.startswith('-'):
                        continue
                    else:
                        board, time, status, warnings = _parse_board_line(line)
                        boot_doc.boards = dict(
                            board=board,
                            time=time,
                            status=status,
                            warnings=warnings
                        )
                elif not line and defconf_section:
                    # Done parsing the report section for this defconfig.
                    defconf_section = False

    return boot_docs


def _parse_board_line(line):
    """Very hackish way of parsing the board line.

    This methods highly depends on how the boot log is built. If that changes
    this can easily break.

    :param line: The line to parse.
    :return A tuple with board name, time taken to boot, the status, and the
        number of warnings.
    """
    warnings = 0

    values = line.split()
    board = values.pop(0)

    time_d = timedelta(
        minutes=float(values[0]), seconds=float(values[2]))

    # Boot duration is calculated as time after 1970-1-1 00:00:00.
    time = datetime(
        1970, 1, 1,
        minute=time_d.seconds / 60,
        second=time_d.seconds % 60,
        microsecond=time_d.microseconds
    )

    values = values[4:]

    status = values.pop(0)
    if len(values) > 1:
        warnings = values[1].strip(')')

    return (board, time, status, warnings)


def _import_all(base_path=BASE_PATH):
    """Handy function to import all boot logs."""
    boot_docs = []

    for job_dir in os.listdir(base_path):
        job_dir = os.path.join(base_path, job_dir)

        if os.path.isdir(job_dir):
            LOG.info("Importing boot logs from %s", job_dir)
            boot_docs.extend(
                _parse_boot_log(boot_log) for boot_log in glob.iglob(
                    os.path.join(job_dir, BOOT_REPORT_PATTERN)
                )
                if os.path.isfile(boot_log)
            )

    return boot_docs


if __name__ == '__main__':
    connection = pymongo.MongoClient()
    database = connection[DB_NAME]

    all_docs = _import_all(database)
    for docs in all_docs:
        save(database, docs)

    connection.disconnect()
