#!/usr/bin/python

"""
    Copyright (c) 2005--2007
    Jan Nieuwenhuizen <janneke@gnu.org>
    Han-Wen Nienhuys <hanwen@xs4all.nl>

    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 2, or (at your option)
    any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program; if not, write to the Free Software
    Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
"""

import os
import re
import string
import sys

sys.path.insert (0, 'lib/')

from misc import *
import gup
import cross
import gub
import settings as settings_mod
import locker

def get_cli_parser ():
    import optparse
    p = optparse.OptionParser ()

    p.usage='''gub-builder.py [OPTION]... [PACKAGE]...

'''
    p.description='Grand Unified Builder.  Specify --package-version to set build version'

    p.add_option ('-B', '--branch', action='append',
                  dest='branches',
                  default=[],
                  metavar='NAME=BRANCH',
                  help='select branch')

    p.add_option ('-k', '--keep', action='store_true',
                  dest='keep_build',
                  default=None,
                  help='leave build and src dir for inspection')

    p.add_option ('-p', '--target-platform', action='store',
                  dest='platform',
                  type='choice',
                  default=None,
                  help='select target platform',
                  choices=settings_mod.platforms.keys ())

    p.add_option ('--inspect', action='store',
                  dest='inspect_key',
                  default=None,
                  help='Key of package to inspect')

    p.add_option ('--inspect-output', action='store',
                  dest='inspect_output',
                  default=None,
                  help='Where to write result of inspection')

    p.add_option ('--offline', action='store_true',
                  dest='offline')

    p.add_option ('--stage', action='store',
                  dest='stage', default=None,
                  help='Force rebuild of stage')

    p.add_option ('--cross-distcc-host', action='append',
                  dest='cross_distcc_hosts', default=[],
                  help='Add another cross compiling distcc host')

    p.add_option ('--native-distcc-host', action='append',
                  dest='native_distcc_hosts', default=[],
                  help='Add another native distcc host')

    p.add_option ('-V', '--verbose', action='store_true',
                  dest='verbose')

    p.add_option ('--lilypond-versions', action='store',
                  default='uploads/lilypond.versions',
                  dest='lilypond_versions')

    p.add_option ('--force-package', action='store_true',
                  default=False,
                  dest='force_package',
                  help='allow packaging of tainted compiles' )

    p.add_option ('--build-source', action='store_true',
                  default=False,
                  dest='build_source',
                  help='build source packages')

    p.add_option ('--lax-checksums',
                  action='store_true',
                  default=False,
                  dest='lax_checksums',
                  help="do not rebuild packages with failing checksums")

    p.add_option ('-l', '--skip-if-locked',
                  default=False,
                  dest="skip_if_locked",
                  action="store_true",
                  help="Return successfully if another build is already running")
    p.add_option ('-j', '--jobs',
                  default="1", action='store',
                  dest='cpu_count',
                  help='set number of simultaneous jobs')

    return p

def checksums_valid (manager, specname, spec_object_dict):
    import pickle
    spec = spec_object_dict[specname]

    valid = True
    for package in spec.get_packages ():
        name = package.name()
        package_dict = manager.package_dict (name)

        valid = (spec.spec_checksum == package_dict['spec_checksum']
                 and spec.source_checksum () == package_dict['source_checksum'])

        hdr = package.expand ('%(split_hdr)s')
        valid = valid and os.path.exists (hdr)
        if valid:
            hdr_dict = pickle.load (open (hdr))
            hdr_sum = hdr_dict['spec_checksum']
            valid = valid and hdr_sum == spec.spec_checksum
            valid = valid and spec.source_checksum () == hdr_dict['source_checksum']

    ## let's be lenient for cross packages.
    ## spec.cross_checksum == manager.package_dict(name)['cross_checksum'])

    return valid

def run_one_builder (options, spec_obj):
    import inspect
    available = dict (inspect.getmembers (spec_obj, callable))
    if options.stage:
        (available[options.stage]) ()
        return

    stages = ['download', 'untar', 'patch',
              'configure', 'compile', 'install',
              'src_package', 'package', 'clean']

    if options.offline:
        stages.remove ('download')

    if not options.build_source:
        stages.remove ('src_package')

    tainted = False
    for stage in stages:
        if (not available.has_key (stage)):
            continue

        if spec_obj.is_done (stage, stages.index (stage)):
            tainted = True
            continue

        spec_obj.os_interface.log_command (' *** Stage: %s (%s)\n'
                                           % (stage, spec_obj.name ()))

        if stage == 'package' and tainted and not options.force_package:
            msg = spec_obj.expand ('''Compile was continued from previous run.
Will not package.
Use

rm %(stamp_file)s

to force rebuild, or

--force-package

to skip this check.
''')
            spec_obj.os_interface.log_command (msg)
            raise 'abort'


        if (stage == 'clean'
            and options.keep_build):
            os.unlink (spec_obj.get_stamp_file ())
            continue

        try:
            (available[stage]) ()
        except SystemFailed:

            ## failed patch will leave system in unpredictable state.
            if stage == 'patch':
                spec_obj.system ('rm %(stamp_file)s')

            raise

        if stage != 'clean':
            spec_obj.set_done (stage, stages.index (stage))

def run_builder (options, settings, manager, names, spec_object_dict):
    PATH = os.environ['PATH']

    ## cross_prefix is also necessary for building cross packages, such as GCC
    os.environ['PATH'] = settings.expand ('%(cross_prefix)s/bin:' + PATH,
                                          locals ())

    ## UGH -> double work, see cross.change_target_packages () ?
    sdk_pkgs = [p for p in spec_object_dict.values ()
                if isinstance (p, gub.SdkBuildSpec)]
    cross_pkgs = [p for p in spec_object_dict.values ()
                  if isinstance (p, cross.CrossToolSpec)]

    extra_build_deps = [p.name () for p in sdk_pkgs + cross_pkgs]
    if not options.stage:

        reved = names[:]
        reved.reverse ()
        for spec_name in reved:
            spec = spec_object_dict[spec_name]
            checksum_ok = (options.lax_checksums
                           or checksums_valid (manager, spec_name,
                                               spec_object_dict))
            for p in spec.get_packages ():
                if (manager.is_installed (p.name ()) and
                    (not manager.is_installable (p.name ())
                     or not checksum_ok)):

                    manager.uninstall_package (p.name ())

    for spec_name in names:
        spec = spec_object_dict[spec_name]
        all_installed = True
        for p in spec.get_packages():
            all_installed = all_installed and manager.is_installed (p.name ())
        if all_installed:
            continue
        checksum_ok = (options.lax_checksums
                       or checksums_valid (manager, spec_name,
                                           spec_object_dict))

        is_installable = forall (manager.is_installable (p.name ())
                                 for p in spec.get_packages ())

        if (options.stage
            or not is_installable
            or not checksum_ok):
            settings.os_interface.log_command ('building package: %s\n'
                                               % spec_name)
            run_one_builder (options, spec)

        for p in spec.get_packages ():
            name = p.name ()
            if not manager.is_installed (name):
                subname = ''
                if spec.name () != p.name ():
                    subname = name.split ('-')[-1]
                if spec.get_conflict_dict ().has_key (subname):
                    for c in spec.get_conflict_dict ()[subname]:
                        if manager.is_installed (c):
                            print '%(c)s conflicts with %(name)s' % locals ()
                            manager.uninstall_package (c)
                manager.unregister_package_dict (p.name ())
                manager.register_package_dict (p.dict ())
                manager.install_package (p.name ())

def get_settings (options):
    # FIXME, move (all these get_setting*) to constructors
    settings = settings_mod.get_settings (options.platform)
    settings.set_branches (options.branches)
    settings.build_source = options.build_source
    settings.cpu_count = options.cpu_count
    settings.set_distcc_hosts (options)
    settings.lilypond_versions = options.lilypond_versions
    settings.options = options ##ugh
    return settings

def inspect (settings, files):
    (names, specs) = gup.get_source_packages (settings, files)
    pm = gup.get_target_manager (settings)
    gup.add_packages_to_manager (pm, settings, specs)
    deps = filter (specs.has_key, names)

    for f in files:
        v =  pm.package_dict (f)[settings.options.inspect_key]
        if settings.options.inspect_output:
            open (settings.options.inspect_output, 'w').write (v)
        else:
            print v
        
def build (settings, files):
    PATH = os.environ['PATH']
    os.environ['PATH'] = settings.expand ('%(local_prefix)s/bin:' + PATH)
    (names, specs) = gup.get_source_packages (settings, files)
    def get_all_deps (name):
        package = specs[name]
        deps = package.get_build_dependencies ()
        if not settings.is_distro:
            deps = [gup.get_base_package_name (d) for d in deps]
        return deps

    deps = gup.topologically_sorted (files, {}, get_all_deps, None)
    if settings.options.verbose:
        print 'deps:' + `deps`

    try:
        pm = gup.get_target_manager (settings)

        ## Todo: have a readonly lock for local platform
    except locker.LockedError:
        print 'another build in progress. Skipping.'
        if settings.options.skip_if_locked:
            sys.exit (0)
        raise

    gup.add_packages_to_manager (pm, settings, specs)
    deps = filter (specs.has_key, names)
    run_builder (settings.options, settings, pm, deps, specs)

def main ():
    cli_parser = get_cli_parser ()
    (options, files) = cli_parser.parse_args ()

    if not options.platform:
        print 'error: no platform specified'
        cli_parser.print_help ()
        sys.exit (2)

    settings = get_settings (options)

    if options.inspect_key:
        inspect (settings, files)
        sys.exit (0)

    build (settings, files)

if __name__ == '__main__':
    main ()
