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

import json
import logging
import os
import tempfile
import types
import unittest

from utils.meta_parser import parse_metadata_file


class TestMetaParser(unittest.TestCase):

    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.temp_metadata = tempfile.NamedTemporaryFile(delete=False)

    def tearDown(self):
        logging.disable(logging.NOTSET)
        try:
            os.unlink(self.temp_metadata.name)
        except Exception:
            pass

    def test_parse_config_file(self):
        file_content = (
            '[DEFAULT]\nbuild_status: PASS\nbuild_log: build.log'
        )

        with open(self.temp_metadata.name, 'w') as w_file:
            w_file.write(file_content)

        expected = dict(build_status='PASS', build_log='build.log')
        metadata = parse_metadata_file(self.temp_metadata.name)

        self.assertEqual(expected, metadata)

    def test_parse_normal_file(self):
        file_content = (
            'build_status: PASS\nbuild_log: build.log\n'
        )

        with open(self.temp_metadata.name, 'w') as w_file:
            w_file.write(file_content)

        expected = dict(build_status='PASS', build_log='build.log')
        metadata = parse_metadata_file(self.temp_metadata.name)

        self.assertEqual(expected, metadata)

    def test_parse_json_file(self):
        expected = dict(build_status='PASS', build_log='build.log')

        try:
            json_tmp = tempfile.NamedTemporaryFile(
                suffix='.json', delete=False
            )

            with open(json_tmp.name, 'w') as w_file:
                json.dump(expected, w_file)

            metadata = parse_metadata_file(json_tmp.name)
            self.assertIsInstance(metadata, types.DictionaryType)
            self.assertEqual(expected, metadata)
        finally:
            os.unlink(json_tmp.name)