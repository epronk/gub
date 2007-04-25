import cross
import gcc
import gub
import glibc
import linux
import targetpackage

binutils_format = 'bz2'
gcc_format = 'bz2'

'''
Configured with: /work/GNU/CodeSourcery/src/gcc-3.4.0/configure 
--target=arm-linux 
--host=i686-host_pc-linux-gnu 
--prefix=/usr/local/arm/gnu/release-3.4.0-vfp 
--with-headers=/usr/local/arm/gnu/release-3.4.0-vfp/arm-linux/include 
--with-local-prefix=/usr/local/arm/gnu/release-3.4.0-vfp/arm-linux 
--disable-nls 
--enable-threads=posix 
--enable-symvers=gnu 
--enable-__cxa_atexit 
--enable-languages=c,c++ 
--enable-shared 
--enable-c99 
--enable-clocale=gnu 
--enable-long-long
'''

code_sourcery = 'http://www.codesourcery.com/public/gnu_toolchain/%(name)s/arm-%(ball_version)s-%(name)s.src.tar.%(format)s'

class Arm_none_elf (gub.BinarySpec, gub.SdkBuildSpec):
    def install (self):
        self.system ('''
mv %(srcdir)s/*gz %(downloads)s
mkdir -p %(install_root)s
''')

class Gcc (gcc.Gcc):
    def patch (self):
        gcc.Gcc.patch (self)
        self.system ('''
cd %(srcdir)s && patch -p1 < %(patchdir)s/gcc-3.4.0-arm-lib1asm.patch
cd %(srcdir)s && patch -p1 < %(patchdir)s/gcc-3.4.0-arm-nolibfloat.patch
''')
    def configure_command (self):
        return (gcc.Gcc.configure_command (self)
                + misc.join_lines ('''
--with-float=soft
#--with-fpu=vfp
'''))

class Gcc_core (gcc.Gcc_core):
    def patch (self):
        gcc.Gcc_core.patch (self)
        self.system ('''
cd %(srcdir)s && patch -p1 < %(patchdir)s/gcc-3.4.0-arm-lib1asm.patch
cd %(srcdir)s && patch -p1 < %(patchdir)s/gcc-3.4.0-arm-nolibfloat.patch
''')
    def configure_command (self):
        return (gcc.Gcc_core.configure_command (self)
                + misc.join_lines ('''
--with-float=soft
#--with-fpu=vfp
'''))

class Glibc (glibc.Glibc):
    def patch (self):
        glibc.Glibc.patch (self)
        self.system ('''
cd %(srcdir)s && patch -p1 < %(patchdir)s/glibc-2.3-wordexp-inline.patch
cd %(srcdir)s && patch -p1 < %(patchdir)s/glibc-2.3-linux-2.4.23-arm-bus-isa.patch
''')
    def configure_command (self):
        return (glibc.Glibc.configure_command (self)
                + misc.join_lines ('''
--without-fp
'''))

class Glibc_core (glibc.Glibc_core):
    def patch (self):
        glibc.Glibc_core.patch (self)
        self.system ('''
cd %(srcdir)s && patch -p1 < %(patchdir)s/glibc-2.3-wordexp-inline.patch
cd %(srcdir)s && patch -p1 < %(patchdir)s/glibc-2.3-linux-2.4.23-arm-bus-isa.patch
''')
    def configure_command (self):
        return (glibc.Glibc_core.configure_command (self)
                + misc.join_lines ('''
--without-fp
'''))

#FIXME, c&p linux.py
import mirrors
import misc
def _get_cross_packages (settings,
                         linux_version, binutils_version, gcc_version,
                         glibc_version, guile_version, python_version):
    configs = []
    if not settings.platform.startswith ('linux'):
        configs = [
            linux.Guile_config (settings).with (version=guile_version),
            linux.Python_config (settings).with (version=python_version),
            ]

    import linux_headers
    import debian
    import binutils
    import gcc
    import glibc
    headers = linux_headers.Linux_headers (settings)\
        .with_tarball (mirror=mirrors.linux_2_6,
                       version=linux_version,
                       format='bz2')
    if settings.package_arch == 'arm':
        headers = debian.Linux_kernel_headers (settings)\
            .with (version=linux_version,
                   strip_components=0,
                   mirror=mirrors.lilypondorg_deb,
                   format='deb')
    sdk = []
    if binutils_version in ('2004-q1a',):
        sdk += Arm_none_elf (settings).with (version=binutils_version,
                                             format='bz2',
                                             mirror=code_sourcery,
                                             strip_components=0),
    return sdk + [
        headers,
        binutils.Binutils (settings).with (version=binutils_version,
                                           format=binutils_format,
                                           mirror=mirrors.gnu),
        Gcc_core (settings).with (version=gcc_version,
                                  mirror=(mirrors.gcc
                                          % {'name': 'gcc',
                                             'ball_version': gcc_version,
                                             'format': gcc_format,}),
                                  format='bz2'),
        Glibc_core (settings).with (version=glibc_version,
                                    mirror=(mirrors.glibc_2_3_snapshots
                                            % {'name': 'glibc',
                                               'ball_version': glibc_version,
                                               'format': 'bz2',}),
                                    format='bz2'),
        Gcc (settings).with (version=gcc_version,
                                 mirror=mirrors.gcc, format=gcc_format),
        Glibc (settings).with (version=glibc_version,
                               mirror=mirrors.glibc_2_3_snapshots,
                               format='bz2'),
        ] + configs



def get_cross_packages (settings):
    return get_cross_packages_pre_eabi (settings)
    #return get_code_sourcery_2004_q1a (settings)

def get_code_sourcery_2004_q1a (settings):
    global binutils_format, gcc_format
    binutils_format = gcc_format = 'gz'
    linux_version = '2.5.999-test7-bk-17'
    binutils_version = '2004-q1a'
    gcc_version = '2004-q1a'
    glibc_version = '2.3-20070416'
    guile_version = '1.6.7'
    python_version = '2.4.1'
    return _get_cross_packages (settings,
                                linux_version, binutils_version,
                                gcc_version, glibc_version,
                                guile_version, python_version)

def get_cross_packages_pre_eabi (settings):
    #linux_version = '2.5.75'
    linux_version = '2.5.999-test7-bk-17'
    #linux_version = '2.4.34'
    binutils_version = '2.16.1'
    gcc_version = '3.4.6'
    glibc_version = '2.3-20070416'
    guile_version = '1.6.7'
    python_version = '2.4.1'
    return _get_cross_packages (settings,
                                linux_version, binutils_version,
                                gcc_version, glibc_version,
                                guile_version, python_version)

def change_target_package (p):
    cross.change_target_package (p)
    return p
