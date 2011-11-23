#!/usr/bin/env python
# -*- coding: utf-8 -*-
try:
    from setuptools import setup
except ImportError:
    from ez_setup import use_setuptools
    use_setuptools()
    from setuptools import setup

setup(
    name='tastymongo',
    version='0.0.1-alpha',
    description='A Mongengine model resource for Django Tastypie',
    author='Niels Sandholt Busch',
    author_email='niels.busch@gmail.com',
    url='https://bitbucket.org/resmio/tastymongo/',
    long_description=open('README', 'r').read(),
    packages=[
        'tastymongo',
    ],
    requires=[
        'django(>=1.3)',
        'mongoengine(>=0.5.2)',
        'django_tastypie(>=0.9.10)'
    ],
    install_requires=[
    ],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Web Environment',
        'Framework :: Django Tastypie',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Utilities'
    ],
)