##############################################################################
#
# Copyright (c) 2013 Zope Corporation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
"""GitHub Repository Management
"""
from __future__ import print_function
import configparser
import json
import optparse
import os
import sys
import urllib.request
from github3 import login

from .util import do

DEFAULT_CONFIG_FILE = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'zope.cfg')

noop = lambda x: x
to_bool = lambda x: x.lower() in ('t', 'true', 'y', 'yes', 'on') or None

CONV_MAP = {
    'email': {'send_from_author': to_bool}
    }

TROVE_TO_TRAVIS_PY_VERSIONS = {
    "Programming Language :: Python :: 2.6": '2.6',
    "Programming Language :: Python :: 2.7": '2.7',
    "Programming Language :: Python :: 3.2": '3.2',
    "Programming Language :: Python :: 3.3": '3.3',
    "Programming Language :: Python :: Implementation :: PyPy": 'pypy',
}

TROVE_TO_TOXENV_VERSIONS = {
    "Programming Language :: Python :: 2.6": 'py26',
    "Programming Language :: Python :: 2.7": 'py27',
    "Programming Language :: Python :: 3.2": 'py32',
    "Programming Language :: Python :: 3.3": 'py33',
    "Programming Language :: Python :: Implementation :: PyPy": 'pypy',
}

def get_sub_ns(config, options, repo=None):
    return {
        'github_username': options.username,
        'github_password': options.password,
        'travis_token': options.token,
        'package': getattr(repo, 'name', None)}

def get_repo_description(name, config, options):
    url = '%s/%s/json' % (config.get('pypi', 'url'), name)
    try:
        data = urllib.request.urlopen(url).read().decode()
    except Exception as err:
        return None
    info = json.loads(data)['info']
    return info['summary']

def get_repo_classifiers(name, config, options):
    url = '%s/%s/json' % (config.get('pypi', 'url'), name)
    try:
        data = urllib.request.urlopen(url).read().decode()
    except:
        return []
    info = json.loads(data)['info']
    return info['classifiers']

def update_travis_yaml(repo, config, options):
    name = repo if isinstance(repo, str) else repo.name
    repos_path = config.get('local', 'packages-dir')
    repo_path = os.path.join(repos_path, name)
    if not os.path.exists(repo_path):
        do(['git', 'clone', config.get('github', 'repo-url') + name],
           cwd=repos_path)
    elif not os.path.exists(os.path.join(repo_path, '.git')):
        print('  * Skipping Travis YAML update')
        print('    (Not a Git checkout: ' + repo_path + ')')
        return
    else:
        do(['git', 'pull', '-r'], cwd=repo_path,
           print_stdout=False, print_cmd=False)
    yaml_path = os.path.join(repo_path, '.travis.yml')
    has_yaml = os.path.exists(yaml_path)
    # Check whether this is a custom Travis configuration file.
    if has_yaml:
        with open(yaml_path, 'r') as file:
            if 'custom' in file.read():
                print('  * Skipping Travis YAML update')
                print('    (The file is marked as custom.)')
                return

    # Check whether .gitignore is too restrictive.
    ignore_path = os.path.join(repo_path, '.gitignore')
    if os.path.exists(ignore_path):
        do(['sed', '-i', 's/^\.\*$/\.installed\.cfg/g', ignore_path])

    classifiers = get_repo_classifiers(name, config, options)
    py_versions = [v for k, v in TROVE_TO_TRAVIS_PY_VERSIONS.items()
                   if k in classifiers]
    toxenvs = [v for k, v in TROVE_TO_TOXENV_VERSIONS.items()
               if k in classifiers]
    if not py_versions:
        py_versions.append('2.7')
    if not toxenvs:
        toxenvs.append('py27')
    ns = {'python_versions': '- ' + '\n    - '.join(sorted(py_versions)),
          'tox_environments': '\n    '.join('- TOXENV=' + e for e in sorted(toxenvs))}

    with open(yaml_path, 'w') as out_file:
        with open(config.get('travis', 'yaml-template'), 'r') as in_file:
            out_file.write(in_file.read().format(**ns))
    if not has_yaml:
        do(['git', 'add', '.travis.yml'], cwd=repo_path)
    do(['git', 'commit', '.travis.yml', '-m', "Updated Travis YAML."],
       cwd=repo_path, print_stdout=False, print_cmd=False, ignore_exit=True)
    do(['git', 'push'], cwd=repo_path, print_stdout=False, print_cmd=False)
    print('  * Updated Travis YAML file.')

def update_hooks(repo, config, options):
    if not options.token:
        sys.exit("Please specify the Travis CI token")
    ns = get_sub_ns(config, options, repo)
    hooks = dict((h.name, h) for h in repo.iter_hooks())
    for name in [section[6:] for section in config.sections()
                 if section.startswith('hooks')]:
        active = config.getboolean('hooks:'+name, 'active', fallback=True)
        events = config.get('hooks:'+name, 'events', fallback='push').split()
        OMAP = CONV_MAP.get(name, {})
        conf = dict(
            [(oname, OMAP.get(oname, noop)(value.format(**ns)))
             for (oname, value) in config.items('hooks:'+name)
             if (oname not in ('active', 'events') and
                 OMAP.get(oname, noop)(value) is not None)])
        if name not in hooks:
            hook = repo.create_hook(name, conf, events=events,
                                    active=active)
            print("  * Created Hook: " + hook.name)
        else:
            hook = hooks[name]
            hook.edit(conf, events=events)
            print("  * Updated Hook: " + hook.name)


def update_teams(org, repo, config, options):
    all_teams = dict((t.name, t) for t in org.iter_teams())
    updated_team_names = [
        t.strip() for t in config.get('github', 'teams').split()]
    repo_teams = [t.name for t in repo.iter_teams()]
    add = set(updated_team_names).difference(set(repo_teams))
    delete = set(repo_teams).difference(set(updated_team_names))
    # Add teams
    for name in add:
        all_teams[name].add_repo(repo.full_name)
        print('  * Added Team: '+name)
    # Delete teams
    for name in delete:
        all_teams[name].remove_repo(repo.full_name)
        print('  * Removed Team: '+name)


def update_repositories(gh, config, options):
    org_name = config.get('github', 'organization')
    org = gh.organization(org_name)

    for name in options.repos:
        print()
        print('=====[ '+name+' ]'+'='*(70-len(name)))
        repo = gh.repository(org_name, name)
        created = False
        if repo is None:
            if not config.getboolean('github', 'create-repo'):
                print("Missing Repository: " + name)
                continue
            repo = org.create_repo(name)
            created = True
            print("Created Repository: " + repo.name)
        else:
            print("Found Repository: " + repo.name)
            if not options.update_repo:
                print("  * Skipping update.")
                continue
        if config.getboolean('github', 'update-title'):
            desc = get_repo_description(name, config, options)
            if desc is not None and desc != repo.description:
                updated = repo.edit(name, description=desc)
                if updated:
                    print("  * Updated Title: " + desc)
                else:
                    print("  * Updated Title: **FAILED**")
            else:
                if desc is None:
                    print("  * No Title found.")
                else:
                    print("  * Title is up-to-date.")
        if config.getboolean('github', 'update-teams'):
            update_teams(org, repo, config, options)
        if config.getboolean('github', 'update-hooks'):
            update_hooks(repo, config, options)
        if (options.update_travis_yaml and
            config.getboolean('github', 'update-travis')):
            if not created:
                update_travis_yaml(repo, config, options)
            else:
                print('  * Skipping Travis YAML file update.')
                print('    (No source code yet.)')


def update_all_repositories(gh, config, options):
    org_name = config.get('github', 'organization')
    org = gh.organization(org_name)
    for repo in org.iter_repos():
        print("Found Repository: " + repo.name)
        if config.getboolean('github', 'update-teams'):
            update_teams(org, repo, config, options)
        if config.getboolean('github', 'update-hooks'):
            update_hooks(repo, config, options)


def get_github(options):
    if not options.username and not options.password:
        sys.exit("Please specify your GitHub username and password")
    return login(options.username, options.password)

def load_config(configfile):
    conf = configparser.ConfigParser()
    conf.read([configfile])
    return conf

def get_options(parser, args=None, defaults=None):
    if args is None:
        args = sys.argv
    options, positional = parser.parse_args(args)
    options.positional = options.repos = positional
    return options

###############################################################################
# Command-line UI

parser = optparse.OptionParser("%prog [options] [PKG1 PKG2 ...]")

config = optparse.OptionGroup(
    parser, "Configuration", "Options that deal with configuring the browser.")

config.add_option(
    '--skip-repo-update', action="store_false", dest='update_repo',
    default=True,
    help="A flag indicating that the repo should not be updated, if they exist.")

config.add_option(
    '--skip-travis-yaml', action="store_false", dest='update_travis_yaml',
    default=True,
    help="A flag indicating that the travis.yml file should not be added.")

config.add_option(
    '--all', action="store_true", dest='all_repos', default=False,
    help="Update all repositories.")

config.add_option(
    '--username', '--user', action="store", dest='username',
    help="Username to access the GitHub Web site.")

config.add_option(
    '--password', '--pwd', action="store", dest='password',
    help="Password to access the GitHub Web site.")

config.add_option(
    '--travis-token', '--token', action="store", dest='token',
    help="The user token used by GitHub to talk with Travis CI.")

config.add_option(
    '--config', '-c', action="store", dest='configfile',
    default=DEFAULT_CONFIG_FILE,
    help="The config file containing a lot of settings.")

parser.add_option_group(config)

# Command-line UI
###############################################################################

def addrepos(args=None):
    if args is None:
        args = sys.argv[1:]

    options = get_options(parser, args)
    gh = get_github(options)
    config = load_config(options.configfile)
    update_repositories(gh, config, options)

def updaterepos(args=None):
    if args is None:
        args = sys.argv[1:]

    options = get_options(parser, args)
    gh = get_github(options)
    config = load_config(options.configfile)
    if options.all_repos:
        update_all_repositories(gh, config, options)
    else:
        update_repositories(gh, config, options)
