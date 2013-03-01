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
"""SVN -> GitHub Repository Migration
"""
from __future__ import print_function
import configparser
import io
import optparse
import os
import subprocess
import sys
import tempfile

from zope.githubsupport import repos

DEFAULT_CONFIG_FILE = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'zope.cfg')

def do(cmd, cwd=None, print_stdout=True):
    print(' '.join(cmd))
    p = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        cwd=cwd)
    out, _ = p.communicate()
    if out and print_stdout:
        print(out.decode())
    if p.returncode != 0:
        sys.exit(p.returncode)


def svn2git(target_path, config, options):
    print('Converting package into Git repository. ' +
          'That may take several minutes.')
    rules_path = options.rules_path
    if rules_path is None:
        rules = []
        for pkg_name in options.repos:
            ns = {'package': pkg_name,
                  'package_regex': pkg_name.replace('.', '\\.'),
                  'package_path': pkg_name.replace('.', '/')}
            rules.append(
                config.get('migrate', 'pkg-rules-template').format(**ns))

        ns = {'packages_rules': '\n\n'.join(rules)}
        rules_path = tempfile.mktemp(pkg_name+'.txt')
        with io.open(rules_path, 'w') as file:
            file.write(
                config.get('migrate', 'rules-template').format(**ns))
        print('***** Created rules file: ' + rules_path)

    do([config.get('migrate', 'svn-all-fast-export'),
        '--svn-branches',
        '--add-metadata-notes',
        '--identity-map', config.get('migrate', 'identity-map'),
        '--rules', rules_path,
        '--stats',
        config.get('migrate', 'svn-mirror'),
        ], cwd=target_path, print_stdout=False)


def push2github(target_path, config, options):
    for pkg_name in options.repos:
        git_path = os.path.join(target_path, pkg_name)
        do(['git', 'remote', 'add', 'origin',
            'git@github.com:%s/%s.git' %(
                    config.get('github', 'organization'), pkg_name)
            ], cwd=git_path)
        do(['git', 'push', '-u', 'origin', '--mirror'], cwd=git_path)


def clean_svn(config, options):
    for pkg_name in options.repos:
        co_path = tempfile.mkdtemp()
        print('Checking out code from SVN into: ' + co_path)
        pkg_path = os.path.join(co_path, pkg_name+'.svn')
        do(['svn', 'co',
            config.get('migrate', 'svn-repos')+pkg_name+'/trunk',
            pkg_path
            ])
        to_delete = [os.path.join(pkg_path, fn)
                     for fn in os.listdir(pkg_path)
                     if fn not in ('.svn',)]
        if len(to_delete):
            do(['svn', 'rm'] + to_delete)
        moved_path = os.path.join(pkg_path, 'MOVED_TO_GITHUB')
        with io.open(moved_path, 'w') as file:
            file.write("See https://github.com/zopefoundation/"+pkg_name)
        do(['svn', 'add', moved_path])
        do(['svn', 'ci', '-m', 'Moved to GitHub.', pkg_path])

def update_ztk(config, options):
    for pkg_name in options.repos:
        do(['sed', '-i',
            's/%s = .*/%s = git \$\{buildout:github\}\/%s/g' %(
                    pkg_name, pkg_name, pkg_name),
            os.path.join(config.get('migrate', 'ztk-path'), 'ztk-sources.cfg')
            ])
        do(['svn', 'ci',
            '-m', pkg_name + ' moved to GitHub.',
            config.get('migrate', 'ztk-path')])


def update_winegg(config, options):
    for pkg_name in options.repos:
        web_path = config.get('migrate', 'wineggbuilder-path')
        do(['sed', '-i',
            's/%s,.*/%s,git:\/\/github.com\/zopefoundation\/%s.git/g' %(
                    pkg_name, pkg_name, pkg_name),
            os.path.join(web_path, 'project-list.cfg')
            ])
        do(['svn', 'ci', '-m', pkg_name+' moved to GitHub.', web_path])


def migrate_packages(config, options):
    if options.create_repos:
        gh = repos.get_github(options)
        repos.update_repositories(gh, config, options)

    git_path = options.git_path
    if git_path is None:
        git_path = tempfile.mkdtemp()
    print('Git Repos Path: ' + git_path)

    if options.convert:
        svn2git(git_path, config, options)

    if options.push:
        push2github(git_path, config, options)

    if options.clean_svn:
        clean_svn(config, options)

    if options.update_ztk:
        update_ztk(config, options)

    if options.update_winegg:
        update_winegg(config, options)


def load_config(configfile):
    conf = configparser.ConfigParser()
    conf.read([configfile])
    return conf


def get_options(parser, args=None, defaults=None):
    if args is None:
        args = sys.argv
    options, positional = parser.parse_args(args)
    if len(positional) == 1:
        positional.append(None)
    options.positional = positional
    options.repos = positional
    return options

###############################################################################
# CLI

parser = optparse.OptionParser("%prog [options] [PKG1 PKG2 ...]")

config = optparse.OptionGroup(
    parser, "Configuration", "Options that deal with migration.")

config.add_option(
    '--create', '-C', action="store_true", dest='create_repos', default=False,
    help="A flag indicating that the GitHub repository should be also created.")

config.add_option(
    '--skip-convert', action="store_false", dest='convert', default=True,
    help="A flag indicating that the SVN to Git conversion should be skipped.")

config.add_option(
    '--skip-push', action="store_false", dest='push', default=True,
    help="A flag indicating that the Git repo should not be pushed to GitHub.")

config.add_option(
    '--skip-clean-svn', action="store_false", dest='clean_svn', default=True,
    help="A flag indicating that the SVN trunk should not be cleaned.")

config.add_option(
    '--skip-update-ztk', action="store_false", dest='update_ztk', default=True,
    help="A flag indicating that the ZTK config file should not be updated.")

config.add_option(
    '--skip-update-winegg', action="store_false", dest='update_winegg',
    default=True,
    help="A flag indicating that the wineggbuilder config file should not "
         "be updated.")

config.add_option(
    '--git-path', action="store", dest='git_path', default=None,
    help="The path to the local Git repository of the package.")

config.add_option(
    '--rules', '-r', action="store", dest='rules_path', default=None,
    help="Path to the rules file. If not specified, a file will be created.")

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

# CLI
###############################################################################

def migrate(args=None):
    if args is None:
        args = sys.argv[1:]

    orig_args = args
    options = get_options(parser, args)
    options.orig_args = orig_args
    config = load_config(options.configfile)
    migrate_packages(config, options)
