"""
This makes the bundle zip files and the json file.
"""

import datetime
import glob
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import zipfile

import requests


def get_current_version():
    path = os.getcwd()
    procs = subprocess.run(
        "git describe --tags --exact-match",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=path,
        shell=True
    )
    if procs.returncode != 0:
        return None
    return procs.stdout.decode("utf8").strip()

def date_to_version(tag):
    # YYYYMMDD
    if re.match('\d\d\d\d\d\d\d\d', tag):
        year = int(tag[2:4]) - 20
        month = int(tag[4:6])
        day = int(tag[6:8])
        return f"{year}.{month}.{day}"
    else:
        return tag

# the date tag for the generated files and stuff
# TODO: retrieve the version number from git or something
# TODO: give each file a different version number possibly
#       (that of the latest released change if possible)
TAG = get_current_version() or datetime.date.today().strftime("%Y%m%d")
VERSION_NUMBER = date_to_version(TAG)
# the dirs for putting the things in it
BUILD_DIR = "_build"
BUILD_DEPS = os.path.join(BUILD_DIR, "deps")
BUILD_RELEASE = os.path.join(BUILD_DIR, "release")
# the bundle commone name and file
BUNDLE_NAME = "circuitpython-keyboard-layouts"
BUNDLE_JSON = os.path.join(BUILD_RELEASE, f"{BUNDLE_NAME}-{TAG}.json")
# platform dependent
BUNDLE_PATH_NAME = f"{BUNDLE_NAME}-{{platform}}-{TAG}"
BUNDLE_DIR = os.path.join(BUILD_DIR, BUNDLE_PATH_NAME)
BUNDLE_ZIP = os.path.join(BUILD_RELEASE, BUNDLE_PATH_NAME + ".zip")
BUNDLE_LIB_DIR = os.path.join(BUNDLE_DIR, "lib")
# py platform directory
BUNDLE_REQ_DIR = os.path.join(BUNDLE_DIR.format(platform="py"), "requirements")
BUNDLE_ZIP_JSON = os.path.join(BUNDLE_DIR.format(platform="py"), f"{BUNDLE_NAME}.json")

MODULES_DIR = "libraries"
REQUIREMENTS_FILE = "requirements-modules.txt"

SET_VERSION = f"__version__ = '{VERSION_NUMBER}'"
THIS_REPOSITORY = "https://github.com/Neradoc/Circuitpython_Keyboard_Layouts.git"

PLATFORMS = ["mpy6", "mpy7"]
PLATFORM_NAMES = {
    "py": "py",
    "mpy6": "6.x-mpy",
    "mpy7": "7.x-mpy",
}

# https://adafruit-circuit-python.s3.amazonaws.com/index.html?prefix=bin/mpy-cross/
# TODO: identify current OS and pick one
MPYCROSS_URL = "https://adafruit-circuit-python.s3.amazonaws.com/bin/mpy-cross/"
MPYCROSSES = {
    "darwin": {
        "mpy6": "mpy-cross-macos-catalina-6.3.0",
        "mpy7": "mpy-cross-macos-universal-7.0.0-alpha.4",
    },
    "linux": {
        "mpy6": "mpy-cross.static-amd64-linux-6.3.0",
        "mpy7": "mpy-cross.static-amd64-linux-7.0.0-alpha.4",
    },
    "win32": {
        "mpy6": "mpy-cross.static-x64-windows-6.3.0.exe",
        "mpy7": "mpy-cross.static-x64-windows-7.0.0-alpha.4.exe",
    },
    "raspbian": {
        "mpy6": "mpy-cross.static-raspbian-6.3.0",
        "mpy7": "mpy-cross.static-raspbian-7.0.0-alpha.4",
    },
}
MPYCROSS = MPYCROSSES[sys.platform]


def fmt(path, platform="py"):
    """shortcut for the py directory"""
    return path.format(platform=PLATFORM_NAMES[platform])


# find in python
def list_all_files(path):
    """clean list of all files in sub folders"""
    pwd = os.getcwd()
    os.chdir(path)
    liste = [
        file
        for file in glob.glob(os.path.join("**"), recursive=True)
        if os.path.isfile(file)
    ]
    os.chdir(pwd)
    return liste


def init_directories():
    """erase and create build directories"""
    # create build directories
    os.makedirs(BUILD_DIR, exist_ok=True)
    os.makedirs(BUILD_DEPS, exist_ok=True)
    os.makedirs(BUILD_RELEASE, exist_ok=True)
    os.makedirs(fmt(BUNDLE_DIR), exist_ok=True)

    # cleanup build directories
    for platform in ["py"] + PLATFORMS:
        bun_dir = BUNDLE_DIR.format(platform=PLATFORM_NAMES[platform])
        zip_file = BUNDLE_ZIP.format(platform=PLATFORM_NAMES[platform])
        if os.path.isdir(bun_dir):
            shutil.rmtree(bun_dir)
        if os.path.isfile(zip_file):
            os.unlink(zip_file)


def make_bundle_files():
    """create the .py bundle directory"""
    # copy all the layouts and keycodes
    shutil.copytree(MODULES_DIR, fmt(BUNDLE_LIB_DIR))

    # change the version number of all the bundles
    py_files = os.path.join(fmt(BUNDLE_LIB_DIR), "**", "*.py")
    for module in glob.glob(py_files, recursive=True):
        with open(module, "r") as fp:
            data = fp.read()
        data = data.replace(
            '\n__version__ = "0.0.0-auto.0"\n',
            f"\n{SET_VERSION}\n",
        )
        with open(module, "w") as fp:
            fp.write(data)

    # list of the modules
    all_modules = [
        mod.replace(".py", "")
        for mod in os.listdir(MODULES_DIR)
        if not mod.startswith(".")
    ]

    json_data = {}

    for module in all_modules:
        # create the requirements directory for each module
        target_dir = os.path.join(BUNDLE_REQ_DIR, module)
        os.makedirs(target_dir, exist_ok=True)
        # copy the common requirements file
        target = os.path.join(target_dir, "requirements.txt")
        shutil.copy(REQUIREMENTS_FILE, target)
        # create the json entry
        json_data[module] = {
            "package": False,
            "pypi_name": "",
            "version": VERSION_NUMBER,
            "repo": THIS_REPOSITORY,
            "path": "lib/" + module,
            "dependencies": [],  # "adafruit_hid"
            "external_dependencies": ["adafruit-circuitpython-hid"],
        }
        # add the dependency to keyboard_layout
        if module.startswith("keyboard_layout_"):
            json_data[module]["dependencies"].append("keyboard_layout")
            with open(target,"a") as fp:
                fp.write("\r\nkeyboard_layout\r\n")

    # create the json file
    with open(BUNDLE_JSON, "w") as out_file:
        json.dump(json_data, out_file, indent=2)


def make_the_mpy_bundles():
    """create the mpy bundle(s) directory(ies) and mpy-cross the modules"""
    # copy for the zips
    shutil.copy(BUNDLE_JSON, fmt(BUNDLE_ZIP_JSON))

    # download the mpycrosses
    for cross in MPYCROSS:
        cross_file = os.path.join(BUILD_DEPS, MPYCROSS[cross])
        if not os.path.isfile(cross_file):
            url = MPYCROSS_URL + MPYCROSS[cross]
            response = requests.get(url)
            with open(cross_file, "wb") as cross_fp:
                cross_fp.write(response.content)
            fstats = os.stat(cross_file)
            os.chmod(cross_file, fstats.st_mode | stat.S_IEXEC)

    # duplicate the py dir to mpy6 and mpy7
    for platform in PLATFORMS:
        cross = os.path.join(BUILD_DEPS, MPYCROSS[platform])
        bun_dir = BUNDLE_DIR.format(platform=PLATFORM_NAMES[platform])
        lib_dir = BUNDLE_LIB_DIR.format(platform=PLATFORM_NAMES[platform])
        shutil.copytree(fmt(BUNDLE_DIR), bun_dir)
        # run mpy-cross in each of those
        for lib_file in glob.glob(os.path.join(lib_dir, "*.py")):
            mpy_file = lib_file.replace(".py", ".mpy")
            subprocess.call([cross, lib_file, "-o", mpy_file])
            os.unlink(lib_file)


def do_the_zips():
    """finally create the zip files for release"""
    # now do the zips
    for platform in ["py"] + PLATFORMS:
        in_path = BUNDLE_PATH_NAME.format(platform=PLATFORM_NAMES[platform])
        bun_dir = BUNDLE_DIR.format(platform=PLATFORM_NAMES[platform])
        zip_file = BUNDLE_ZIP.format(platform=PLATFORM_NAMES[platform])
        all_files = list_all_files(bun_dir)
        with zipfile.ZipFile(zip_file, "w") as bundle:
            # metadata (bundler version)
            # build_metadata = {"build-tools-version": build_tools_version}
            # bundle.comment = json.dumps(build_metadata).encode("utf-8")
            for ffile in all_files:
                in_file_path = in_path + "/" + ffile
                bundle.write(os.path.join(bun_dir, ffile), in_file_path)


if __name__ == "__main__":
    init_directories()
    make_bundle_files()
    make_the_mpy_bundles()
    do_the_zips()
