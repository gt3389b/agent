"""
Copyright (c) 2016 John Blackford

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

# File Name: agent_db.py
#
# Description: Rudimentary Agent Database
#
# Functionality:
#  - Dictionary as a database (key=full parameter path, value=parameter value)
#  - The database is initialized from a JSON formatted file
#  - Get command for full parameter path
#  - Update command for full parameter path
#  - Insert command for tables
#  - Delete command for tables
#  - Find commands for wild-carded or partial parameter paths (returns full parameter paths)
#  --- find_params: find parameter paths
#  --- find_instances: find multi-object instance partial paths
#  --- find_impl_objects: find implemented object partial paths
#  - Save command (saves the contents of the database back to a file)
#
"""


import re
import json
import time
import logging
import datetime
import threading
import os
import shutil
# import prometheus_client

from agent import utils

# Metrics disabled - prometheus_client not installed
# # pylint: disable-msg=no-value-for-parameter
# DB_GET_SUMMARY_METRIC = \
#     prometheus_client.Summary("database_get_processing_seconds",
#                               "Time spent handling Database Get Call")
# # pylint: disable-msg=no-value-for-parameter
# DB_UPDATE_SUMMARY_METRIC = \
#     prometheus_client.Summary("database_update_processing_seconds",
#                               "Time spent handling Database Update Call")
# # pylint: disable-msg=no-value-for-parameter
# DB_INSERT_SUMMARY_METRIC = \
#     prometheus_client.Summary("database_insert_processing_seconds",
#                               "Time spent handling Database Insert Call")
# # pylint: disable-msg=no-value-for-parameter
# DB_DELETE_SUMMARY_METRIC = \
#     prometheus_client.Summary("database_delete_processing_seconds",
#                               "Time spent handling Database Delete Call")
# # pylint: disable-msg=no-value-for-parameter
# DB_FIND_PARAMS_SUMMARY_METRIC = \
#     prometheus_client.Summary("database_find_params_processing_seconds",
#                               "Time spent handling Database FindParams Call")
# # pylint: disable-msg=no-value-for-parameter
# DB_FIND_INSTANCES_SUMMARY_METRIC = \
#     prometheus_client.Summary("database_find_instances_processing_seconds",
#                               "Time spent handling Database FindInstances Call")
# # pylint: disable-msg=no-value-for-parameter
# DB_FIND_OBJECTS_SUMMARY_METRIC = \
#     prometheus_client.Summary("database_find_objects_processing_seconds",
#                               "Time spent handling Database FindObjects Call")
# # pylint: disable-msg=no-value-for-parameter
# DB_FIND_IMPL_OBJECTS_SUMMARY_METRIC = \
#     prometheus_client.Summary("database_find_impl_objects_processing_seconds",
#                               "Time spent handling Database FindImplObjects Call")


class Database:
    """Represents a simple database"""
    def __init__(self, dm_filename, db_filename, net_intf):
        """Initialize the DB from a file"""
        self._net_intf = net_intf
        self._db_filename = db_filename
        self._file_write_lock = threading.Lock()
        self._new_inst_num_lock = threading.Lock()
        self._start_time = time.time()
        self._supported_insert_path_list = [
            "Device.Services.HomeAutomation.{i}.Camera.{i}.Pic."
        ]
        self._supported_delete_path_list = [
            "Device.Services.HomeAutomation.{i}.Camera.{i}.Pic.{i}."
        ]

        logger = logging.getLogger(self.__class__.__name__)
        logger.debug("Initializing the Database...")

        # Retrieve the Implemented Data Model
        with open(dm_filename, "r") as dm_in_json:
            try:
                self._dm = json.load(dm_in_json)
            except ValueError as parse_err:
                self._dm = {}
                logger.error("Implemented Data Model is NOT properly formatted JSON: %s", parse_err)

        # Restore from defaults if runtime database doesn't exist
        if not os.path.exists(db_filename):
            logger.info("Runtime database not found at %s, restoring from defaults", db_filename)
            self._restore_from_defaults(db_filename)

        # Retrieve the Persisted Database
        with open(db_filename, "r") as db_in_json:
            try:
                self._db = json.load(db_in_json)
            except ValueError as parse_err:
                self._db = {}
                logger.error("Persisted Database is NOT properly formatted JSON: %s", parse_err)

    # @DB_GET_SUMMARY_METRIC.time()
    def get(self, path):
        """Retrieve the value of the incoming path, or throw a NoSuchPathError"""
        value = None

        if path in self._db:
            if self._db[path] == "__UPTIME__":
                value = int(time.time() - self._start_time)
            elif self._db[path] == "__IPADDR__":
                value = utils.IPAddr.get_ip_addr(self._net_intf)
            elif self._db[path] == "__CURR_TIME__":
                time_zone = self._db["Device.Time.LocalTimeZone"]
                tz_part = time_zone.split(",")[0]
                now = datetime.datetime.now()
                now_str = now.strftime("%Y-%m-%dT%H:%M:%S")
                if tz_part == "CST6CDT":
                    now_str += "-06:00"
                else:
                    now_str += "Z"
                value = now_str
            elif self._db[path] == "__NUM_ENTRIES__":
                inst_path = re.sub(r'NumberOfEntries', '.', path)
                found_instances = self.find_instances(inst_path)
                value = len(found_instances)
            else:
                value = self._db[path]
        else:
            raise NoSuchPathError(path)

        return value

    # @DB_UPDATE_SUMMARY_METRIC.time()
    def update(self, path, value):
        """Change the value of the incoming path, or throw a NoSuchPathError"""
        if path in self._db:
            self._db[path] = value
            self._save()
        else:
            raise NoSuchPathError(path)
    
    def set(self, path, value):
        """Alias for update() - change the value of the incoming path"""
        return self.update(path, value)

    # @DB_FIND_PARAMS_SUMMARY_METRIC.time()
    def find_params(self, path):
        """Retrieve a set of parameter paths that match the incoming path"""
        found_keys = []
        is_implemented_path = False
        logger = logging.getLogger(self.__class__.__name__)

        # Turn the incoming path into a regex to validate it is in the implemented data model
        dm_regex_str = self._dm_regex(path, path.endswith("."))
        logger.debug("find_params: Using regex \"%s\" to validate Path [%s] is in the Implemented Data Model",
                     dm_regex_str, path)

        # Turn the incoming path into a regex to get the matching paths
        db_regex_str = self._db_regex(path, path.endswith("."))
        logger.debug("find_params: Using regex \"%s\" to retrieve values from the Database for Path [%s]",
                     db_regex_str, path)

        # Validate that path is in the Implemented Data Model
        dm_keys = self._dm.keys()
        for dm_key in dm_keys:
            if re.fullmatch(dm_regex_str, dm_key) is not None:
                is_implemented_path = True
                break

        # If the path is Valid then retrieve the matching paths
        if is_implemented_path:
            for param_path in self._db:
                if re.fullmatch(db_regex_str, param_path) is not None:
                    path_parts = param_path.split(".")
                    path_part_len = len(path_parts) - 1

                    if not self._is_meta_parameter(path_parts, path_part_len):
                        found_keys.append(param_path)
        else:
            raise NoSuchPathError(path)

        return found_keys

    def is_param_writable(self, param_path):
        """Validate whether the supplied parameter path is readWrite (return True)"""
        is_writable = False
        dm_param_path = self._generic_dm_path(param_path)

        # Validate that path is in the Implemented Data Model
        if dm_param_path in self._dm:
            if self._dm[dm_param_path] == "readWrite":
                is_writable = True
        else:
            raise NoSuchPathError(dm_param_path)

        return is_writable

    # @DB_FIND_INSTANCES_SUMMARY_METRIC.time()
    def find_instances(self, partial_path):
        """Retrieve a set of object instance paths that match the incoming path"""
        found_keys = []
        is_implemented_path = False
        logger = logging.getLogger(self.__class__.__name__)

        if partial_path.endswith("."):
            # Turn the incoming path into a regex to validate it is in the implemented data model
            dm_regex_str = self._dm_regex(partial_path, True)
            logger.debug("find_instances: Using regex \"%s\" to validate Path [%s] is in the Implemented Data Model",
                         dm_regex_str, partial_path)

            # Turn the incoming path into a regex to get the matching paths
            db_regex_str = self._db_regex(partial_path, True)
            logger.debug("find_instances: Using regex \"%s\" to retrieve values from the Database for Path [%s]",
                         db_regex_str, partial_path)
        else:
            raise NoSuchPathError(partial_path)

        # length minus 1 due to the ending "." causing 1 more split
        partial_path_part_len = len(partial_path.split(".")) - 1

        # Validate that path is in the Implemented Data Model
        for dm_key in self._dm:
            if re.fullmatch(dm_regex_str, dm_key) is not None:
                # Validate that the partial_path is a multi-instance object
                dm_key_parts = dm_key.split(".")
                if dm_key_parts[partial_path_part_len] == "{i}":
                    is_implemented_path = True
                    break

        # If the path is Valid then retrieve the matching paths
        if is_implemented_path:
            for path in self._db:
                if re.fullmatch(db_regex_str, path) is not None:
                    # We only want the path to the next level (instance identifiers)
                    path_parts = path.split(".")
                    built_path = utils.PathHelper.build_path_from_parts(path_parts, partial_path_part_len)
                    found_key = built_path + path_parts[partial_path_part_len] + "."

                    if not self._is_meta_parameter(path_parts, partial_path_part_len):
                        # Only add it to found_keys if we haven't done so already
                        if found_key not in found_keys:
                            found_keys.append(found_key)
        else:
            raise NoSuchPathError(partial_path)

        return found_keys

    # @DB_FIND_OBJECTS_SUMMARY_METRIC.time()
    def find_objects(self, partial_path):
        """Retrieve a set of instantiated object paths that match the incoming path"""
        found_keys = []
        is_implemented_path = False
        logger = logging.getLogger(self.__class__.__name__)

        if partial_path.endswith("."):
            # Turn the incoming path into a regex to validate it is in the implemented data model
            dm_regex_str = self._dm_regex(partial_path, True)
            logger.debug("find_objects: Using regex \"%s\" to validate Path [%s] is in the Implemented Data Model",
                         dm_regex_str, partial_path)

            # Turn the incoming path into a regex to get the matching paths
            db_regex_str = self._db_regex(partial_path, True)
            logger.debug("find_objects: Using regex \"%s\" to retrieve values from the Database for Path [%s]",
                         db_regex_str, partial_path)
        else:
            raise NoSuchPathError(partial_path)

        # length minus 1 due to the ending "." causing 1 more split
        partial_path_part_len = len(partial_path.split(".")) - 1

        # Validate that path is in the Implemented Data Model
        for dm_key in self._dm:
            if re.fullmatch(dm_regex_str, dm_key) is not None:
                is_implemented_path = True
                break

        # If the path is Valid then retrieve the matching paths
        if is_implemented_path:
            for path in self._db:
                if re.fullmatch(db_regex_str, path) is not None:
                    # We only want the path to the next level (instance identifiers)
                    path_parts = path.split(".")
                    found_key = utils.PathHelper.build_path_from_parts(path_parts, partial_path_part_len)

                    if found_key not in found_keys:
                        found_keys.append(found_key)
        else:
            raise NoSuchPathError(partial_path)

        return found_keys

    # @DB_FIND_IMPL_OBJECTS_SUMMARY_METRIC.time()
    def find_impl_objects(self, partial_path, next_level):
        """Retrieve a set of implemented object paths that match the incoming path"""
        found_keys = []
        is_implemented_path = False
        logger = logging.getLogger(self.__class__.__name__)
        generic_partial_path = self._generic_dm_path(partial_path)

        if partial_path.endswith("."):
            # Turn the incoming path into a regex to validate it is in the implemented data model
            dm_regex_str = self._dm_regex(partial_path, True)
            logger.debug(
                "find_impl_objects: Using regex \"%s\" to validate Path [%s] is in the Implemented Data Model",
                dm_regex_str, partial_path)
        else:
            raise NoSuchPathError(partial_path)

        # length minus 1 due to the ending "." causing 1 more split
        partial_path_part_len = len(partial_path.split(".")) - 1

        # Validate that path is in the Implemented Data Model
        for dm_key in self._dm:
            if re.fullmatch(dm_regex_str, dm_key) is not None:
                logger.debug("find_impl_objects: Found full match: %s", dm_key)
                found_key = None
                key_parts = dm_key.split(".")
                key_parts_len = len(key_parts)
                is_implemented_path = True

                if next_level:
                    if key_parts_len > partial_path_part_len + 1:
                        built_path = utils.PathHelper.build_path_from_parts(key_parts, partial_path_part_len)
                        found_key = built_path + key_parts[partial_path_part_len] + "."
                    else:
                        logger.debug("find_impl_objects: key parts [%s] less than partial path parts [%s]",
                                     str(key_parts_len), str(partial_path_part_len + 1))
                else:
                    inx = 0
                    found_key = ""
                    while inx < (key_parts_len - 1):
                        found_key += key_parts[inx]
                        found_key += "."
                        inx += 1

                # Only add it to found_keys if we haven't done so already
                if found_key is not None:
                    logger.debug("find_impl_objects: Found key: %s", found_key)
                    if found_key not in found_keys:
                        logger.debug("find_impl_objects: Found key [%s] not already in the list", found_key)
                        # Don't add the incoming partial_path
                        if not found_key == generic_partial_path:
                            logger.debug("find_impl_objects: Adding found key [%s] to the list", found_key)
                            found_keys.append(found_key)

        # If the path is Valid then retrieve the matching paths
        if not is_implemented_path:
            raise NoSuchPathError(partial_path)

        return found_keys

    # @DB_INSERT_SUMMARY_METRIC.time()
    def insert(self, partial_path):
        """Insert a new object instance for any multi-instance path in the DM.

        Returns the new instance number.
        """
        logger = logging.getLogger(self.__class__.__name__)

        # Verify the path exists as a multi-instance object in the DM
        if not self.find_impl_objects(partial_path, True):
            raise NoSuchPathError(partial_path)

        # Derive the generic DM path (strip any instance numbers already present)
        dm_path = self._generic_dm_path(partial_path)

        with self._new_inst_num_lock:
            # Read or initialise the next-instance counter stored at the TABLE level
            next_inst_num_key = partial_path + "__NextInstNum__"
            next_inst_num = self._db.get(next_inst_num_key, 1)

            inst_path = partial_path + str(next_inst_num) + "."

            # Create DB entries for every leaf parameter defined in the DM for this instance type
            # e.g. dm_path = "Device.LocalAgent.Subscription."
            #      inst_dm_prefix = "Device.LocalAgent.Subscription.{i}."
            inst_dm_prefix = dm_path + "{i}."
            created_any = False
            for dm_key in self._dm:
                if dm_key.startswith(inst_dm_prefix):
                    param_suffix = dm_key[len(inst_dm_prefix):]
                    # Skip nested multi-instance objects (contain another {i})
                    if "{i}" in param_suffix:
                        continue
                    # Only leaf parameters (no further sub-object dots)
                    if "." not in param_suffix:
                        self._db[inst_path + param_suffix] = ""
                        created_any = True

            if not created_any:
                raise NoSuchPathError(partial_path)

            # Bump the counter and persist
            self._db[next_inst_num_key] = next_inst_num + 1
            self._save()

        logger.info("insert: Created instance %s", inst_path)
        return next_inst_num

    # @DB_DELETE_SUMMARY_METRIC.time()
    def delete(self, partial_path):
        """Remove an existing object instance and all its parameters."""
        logger = logging.getLogger(self.__class__.__name__)

        # Verify the object exists in the DB
        if not self.find_objects(partial_path):
            raise NoSuchPathError(partial_path)

        # Build a regex matching all keys under this instance path
        db_regex = self._db_regex(partial_path, True)
        keys_to_delete = [k for k in list(self._db.keys()) if re.fullmatch(db_regex, k)]

        for key in keys_to_delete:
            del self._db[key]

        self._save()
        logger.info("delete: Removed %d keys under %s", len(keys_to_delete), partial_path)

    def _db_regex(self, path, partial_path):
        """Generate a regex for determining whether or note a path is in the DB"""
        db_regex_str = "^" + path
        # Assuming that the internal storage is instance number based
        db_regex_str = re.sub(r'\.\*\.', r'.[0-9]+.', db_regex_str)
        db_regex_str = re.sub(r'\.', r'\.', db_regex_str)

        if partial_path:
            db_regex_str = db_regex_str + ".*"

        return db_regex_str

    def _dm_regex(self, path, partial_path):
        """Generate a regex for determining whether or not a path is in the DM"""
        dm_regex_str = "^" + path  # Starts with
        dm_regex_str = re.sub(r'\.[0-9]+\.', r'.{i}.', dm_regex_str)  # Instance Number Addressing
        dm_regex_str = re.sub(r'\.\*\.', r'.{i}.', dm_regex_str)  # Wild-card Searching
        dm_regex_str = re.sub(r'\.', r'\.', dm_regex_str)  # Replace '.' with explicit '.' search

        if partial_path:
            dm_regex_str = dm_regex_str + ".*"

        return dm_regex_str

    def _generic_dm_path(self, path):
        """Turn a DM Path into a Generic one by replacing instance numbers and wildcards"""
        generic_path = re.sub(r'\.[0-9]+\.', r'.{i}.', path)  # Instance Number Addressing
        generic_path = re.sub(r'\.\*\.', r'.{i}.', generic_path)  # Wild-card Searching

        return generic_path

    def _is_meta_parameter(self, path_parts, partial_path_part_len):
        """Determine if the parameter is a meta parameter"""
        return path_parts[partial_path_part_len].startswith("__") and \
               path_parts[partial_path_part_len].endswith("__")

    def _save(self):
        """Save the contents of the DB back into the File"""
        with self._file_write_lock:
            with open(self._db_filename, "w") as db_file:
                json.dump(self._db, db_file, indent=4)

    def _get_defaults_path(self, runtime_path):
        """Convert runtime database path to defaults path"""
        # Convert: database/runtime/test-db.json -> database/defaults/test-defaults.json
        if "/runtime/" in runtime_path:
            defaults_path = runtime_path.replace("/runtime/", "/defaults/")
            defaults_path = defaults_path.replace("-db.json", "-defaults.json")
            return defaults_path
        else:
            # Legacy path format - look for defaults file in same directory
            base_dir = os.path.dirname(runtime_path)
            filename = os.path.basename(runtime_path)
            defaults_filename = filename.replace("-db.json", "-defaults.json")
            return os.path.join(base_dir, "defaults", defaults_filename)

    def _restore_from_defaults(self, runtime_path):
        """Restore database from factory defaults"""
        logger = logging.getLogger(self.__class__.__name__)
        defaults_path = self._get_defaults_path(runtime_path)

        if not os.path.exists(defaults_path):
            logger.error("Factory defaults not found at %s", defaults_path)
            raise FileNotFoundError(f"Factory defaults not found at {defaults_path}")

        # Ensure runtime directory exists
        runtime_dir = os.path.dirname(runtime_path)
        os.makedirs(runtime_dir, exist_ok=True)

        # Copy defaults to runtime
        logger.info("Restoring database from %s to %s", defaults_path, runtime_path)
        shutil.copy2(defaults_path, runtime_path)

    def _create_backup(self):
        """Create a timestamped backup of the current database"""
        logger = logging.getLogger(self.__class__.__name__)
        
        # Determine backup directory
        db_dir = os.path.dirname(self._db_filename)
        if "/runtime/" in self._db_filename:
            backup_dir = os.path.join(os.path.dirname(db_dir), "backups")
        else:
            backup_dir = os.path.join(db_dir, "backups")
        
        os.makedirs(backup_dir, exist_ok=True)

        # Create timestamped backup filename
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.basename(self._db_filename)
        backup_filename = f"{timestamp}_{filename}"
        backup_path = os.path.join(backup_dir, backup_filename)

        # Copy current database to backup
        logger.info("Creating backup at %s", backup_path)
        shutil.copy2(self._db_filename, backup_path)
        return backup_path

    def factory_reset(self):
        """Reset database to factory defaults"""
        logger = logging.getLogger(self.__class__.__name__)
        logger.info("Performing factory reset on database %s", self._db_filename)

        # Create backup before reset
        backup_path = self._create_backup()
        logger.info("Created backup at %s before factory reset", backup_path)

        # Restore from defaults
        self._restore_from_defaults(self._db_filename)

        # Reload database from file
        with open(self._db_filename, "r") as db_in_json:
            try:
                self._db = json.load(db_in_json)
                logger.info("Database successfully reset to factory defaults")
            except ValueError as parse_err:
                self._db = {}
                logger.error("Error loading database after factory reset: %s", parse_err)

        # Reset uptime
        self._start_time = time.time()



class NoSuchPathError(Exception):
    """A Database NoSuchPath Error"""
    def __init__(self, value):
        """Initialize the Exception"""
        Exception.__init__(self)
        self.value = value

    def __str__(self):
        """Return the String value of the Exception"""
        return repr(self.value)
