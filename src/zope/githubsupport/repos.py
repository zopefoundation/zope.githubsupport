##############################################################################
#
# Copyright (c) 2009 Zope Corporation and Contributors.
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
import optparse
import os
import sys
from github3 import login

DEFAULT_CONFIG_FILE = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'zope.cfg')

def add_hooks(repo, config, options):
    for name in [section[6:] for section in config.sections()
                 if section.startswith('hooks')]:
        active = config.getboolean('hooks:'+name, 'active', fallback=True)
        conf = dict(config.items('hooks:'+name))
        conf.pop('active')
        hook = repo.create_hook(name, conf, active=active)
        if hook is None:
            print("  Ignored Hook: " + name)
        else:
            print("  * Created Hook: " + hook.name)

def add_repository(gh, config, options):
    org_name = config.get('github', 'organization')
    name, desc = options.positional
    repo = gh.repository(org_name, name)
    if repo is None:
        org = gh.organization()
        repo = org.create_repo(name, description=desc)
        print("Created Repository: " + repo.name)
    else:
        print("Found Repository: " + repo.name)
    add_hooks(repo, config, options)

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
    options.positional = positional
    return options

###############################################################################
# Command-line UI

parser = optparse.OptionParser("%prog [options] REPOS DESC")

config = optparse.OptionGroup(
    parser, "Configuration", "Options that deal with configuring the browser.")

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
    add_repository(gh, config, options)
