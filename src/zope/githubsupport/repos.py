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

DEFAULT_CONFIG_FILE = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'zope.cfg')

noop = lambda x: x
to_bool = lambda x: x.lower() in ('t', 'true', 'y', 'yes', 'on') or None

CONV_MAP = {
    'email': {'send_from_author': to_bool}
    }

def get_repo_description(name, config, options):
    url = '%s/%s/json' % (config.get('pypi', 'url'), name)
    try:
        data = urllib.request.urlopen(url).read().decode()
    except:
        return None
    info = json.loads(data)['info']
    return info['summary']

def update_hooks(repo, config, options):
    hooks = dict((h.name, h) for h in repo.iter_hooks())
    for name in [section[6:] for section in config.sections()
                 if section.startswith('hooks')]:
        active = config.getboolean('hooks:'+name, 'active', fallback=True)
        OMAP = CONV_MAP.get(name, {})
        conf = dict(
            [(oname, OMAP.get(oname, noop)(value))
             for (oname, value) in config.items('hooks:'+name)
             if (oname not in ('active',) and
                 OMAP.get(oname, noop)(value) is not None)])
        if name not in hooks:
            hook = repo.create_hook(name, conf, active=active)
            print("  * Created Hook: " + hook.name)
        else:
            hook = hooks[name]
            hook.edit(name, conf)
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
        desc = get_repo_description(name, config, options)
        repo = gh.repository(org_name, name)
        if repo is None:
            repo = org.create_repo(name, description=desc)
            print("Created Repository: " + repo.name)
        else:
            print("Found Repository: " + repo.name)
        if desc is not None and desc != repo.description:
            updated = repo.edit(name, description=desc)
            if updated:
                print("Updated Title: " + desc)
            else:
                print("Updated Title: **FAILED**")
        update_teams(org, repo, config, options)
        update_hooks(repo, config, options)

def update_all_repositories(gh, config, options):
    org_name = config.get('github', 'organization')
    org = gh.organization(org_name)
    for repo in org.iter_repos():
        print("Found Repository: " + repo.name)
        update_teams(org, repo, config, options)
        update_hooks(repo, config, options)


def get_github(options):
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
    '--all', action="store_true", dest='all_repos', default=False,
    help="Update all repositories.")

config.add_option(
    '--username', '--user', action="store", dest='username',
    help="Username to access the GitHub Web site.")

config.add_option(
    '--password', '--pwd', action="store", dest='password',
    help="Password to access the GitHub Web site.")

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
