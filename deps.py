import os
import re
import sys
import json
import shutil
import urllib
import httplib
import warnings
import traceback
import functools
import xmlrpclib
import subprocess
from pkg_resources import parse_version, parse_requirements

from concurrent.futures import ThreadPoolExecutor


def dload(storage_dir, (idx, package)):
    if idx % 100 == 99:
        print "Processing {0} package".format(idx + 1)
    try:
        client = xmlrpclib.ServerProxy('https://pypi.python.org/pypi')
        releases = client.package_releases(package)
        _, latest = max((parse_version(ver), ver) for ver in releases)

        for ext in ('tar.gz', 'zip'):
            fname = "{0}-{1}.{2}".format(package, latest, ext)

            head_url = "/packages/source/{0}/{1}/{2}".format(package[0], package, fname)

            conn = httplib.HTTPSConnection("pypi.python.org")
            conn.request("HEAD", head_url)
            if conn.getresponse().status != 200:
                continue

            url = "http://pypi.python.org" + head_url
            dst = os.path.join(storage_dir, fname)
            urllib.urlretrieve(url, dst)
            return package, latest, fname
        return package, None, "Failed to found link"
    except Exception as exc:
        return package, None, "Failed to process: " + str(exc)


rr = re.compile(r'(?ims)"?install_requires"?\s*(=|:)\s*\[(?P<deps>.*?)\]')


def analyze_package((idx, path)):
    # if idx % 100 == 99:
    #     print "Processing {0} package".format(idx + 1)

    package = os.path.basename(path).rsplit('-', 1)[0]
    try:
        return _analyze_package(path, package)
    except:
        # print package + "\n" + traceback.format_exc() + "\n",
        return package, None


def _analyze_package(path, package):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        dname = os.tmpnam()

    os.mkdir(dname)
    arch_name = os.path.join(dname, os.path.basename(path))
    new_files = []

    if path.endswith('.zip'):
        arch_name = arch_name.rsplit(".", 1)[0] + ".zip"
        shutil.copyfile(path, arch_name)
        cmd = "cd {0} ; unzip {1} >/dev/null 2>&1".format(dname, arch_name)
        subprocess.check_call(cmd, shell=True)
        new_files = set(os.listdir(dname)) - set([os.path.basename(arch_name)])
    elif path.endswith('.tar.gz'):
        shutil.copyfile(path, arch_name)
        cmd = "cd {0} ; tar -zxvf {1} >/dev/null 2>&1".format(dname, arch_name)
        subprocess.check_call(cmd, shell=True)
        new_files = set(os.listdir(dname)) - set([os.path.basename(arch_name)])

    if len(new_files) == 1:
        setup_py = os.path.join(dname, list(new_files)[0], 'setup.py')
        if not os.path.isfile(setup_py):
            setup_py = None

        requirements_txt = os.path.join(dname, list(new_files)[0], 'requirements.txt')
        if not os.path.isfile(requirements_txt):
            requirements_txt = None
    else:
        setup_py = None
        requirements_txt = None

    res = None
    if requirements_txt is not None:
        try:
            res = [next(parse_requirements(line)).project_name
                   for line in open(requirements_txt)
                   if line.strip() != ""
                   and not line.strip().startswith('#')
                   and not line.strip().startswith('-')]
        except:
            # print package + " requirements.txt - BROKEN\n" + traceback.format_exc()
            pass

    if setup_py is not None and res is None:
        data = open(setup_py).read()
        re_res = rr.search(data)
        if re_res is not None:
            sres = re_res.group('deps').strip()
            if sres == "":
                res = []
            else:
                sres_list = [i.strip() for i in eval('[\n' + sres + '\n]') if i.strip() != '']
                res = [next(parse_requirements(i)).project_name for i in sres_list]
        elif 'install_requires' not in data:
            res = []

    shutil.rmtree(dname)
    return package, res


def download_all(store_path):
    client = xmlrpclib.ServerProxy('https://pypi.python.org/pypi')
    with ThreadPoolExecutor(64) as pool:
        with open(os.path.join(store_path, 'index.js'), 'w') as fd:
            fd.write("[\n")
            dload_1p = functools.partial(dload, store_path)
            it = pool.map(dload_1p, enumerate(client.list_packages()))
            for package, version, fname in it:
                fd.write(json.dumps((package, version, fname)) + ",\n")
                fd.flush()
            fd.write("]\n")


store_path = sys.argv[1]
# download_all(store_path)
packages = []
for arch in sorted(os.listdir(store_path)):
    path = os.path.join(store_path, arch)
    if os.path.isfile(path):
        packages.append(path)

with ThreadPoolExecutor(64) as pool:
    for package, deps in pool.map(analyze_package, enumerate(packages)):
        if deps is None:
            print package + ", null"
        else:
            print package + ',' + ','.join(deps)
