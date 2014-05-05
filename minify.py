#!/usr/bin/env python
# -*- coding: utf-8 -*-


import argparse
import logging
import os
import random
import re
#pylint: disable=W0402
import string
import subprocess
import sys
import tempfile

from htmlmin.minify import html_minify
import slimit


logging.basicConfig()
LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)
u"""Default logger"""


STYLE_OPENING_TAG = '<style'
STYLE_CLOSING_TAG = 'style>'
SCRIPT_OPENING_TAG = '<script'
SCRIPT_CLOSING_TAG = 'script>'

DJANGO_COMMENT_OPENING_TAG = '{#'
DJANGO_COMMENT_CLOSING_TAG = '#}'
DJANGO_VARIABLE_OPENING_TAG = '{{'
DJANGO_VARIABLE_CLOSING_TAG = '}}'

TAGS_PATTERN = re.compile('({}.*?{}|{}.*?{})'.format(
        re.escape(STYLE_OPENING_TAG), re.escape(STYLE_CLOSING_TAG),
        re.escape(SCRIPT_OPENING_TAG), re.escape(SCRIPT_CLOSING_TAG)))
STYLE_PATTERN = re.compile('({}.*?{}|{}.*?{})'.format(
        re.escape(STYLE_OPENING_TAG), re.escape('>'),
        re.escape('<'), re.escape(STYLE_CLOSING_TAG)))
SCRIPT_PATTERN = re.compile('({}.*?{}|{}.*?{})'.format(
        re.escape(SCRIPT_OPENING_TAG), re.escape('>'),
        re.escape('<'), re.escape(SCRIPT_CLOSING_TAG)))
DJANGO_COMMENT_PATTERN = re.compile('{0}.*?{1}'.format(
    re.escape(DJANGO_COMMENT_OPENING_TAG), re.escape(DJANGO_COMMENT_CLOSING_TAG)))
DJANGO_VARIABLE_PATTERN = re.compile('{0}.*?{1}'.format(
    re.escape(DJANGO_VARIABLE_OPENING_TAG), re.escape(DJANGO_VARIABLE_CLOSING_TAG)))


class CSSMinifyError(Exception):
    u"""Error while running sass compression."""


def get_arguments(argv):
    u"""Parse the command arguments."""

    parser = argparse.ArgumentParser(prog=u'minify',
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument(u'-i', u'--input', dest=u'input', required=True,
            help=u'the HTML file to be compressed.')
    parser.add_argument(u'-o', u'--output', dest=u'output', required=True,
            help=(u'the output HTML file path.\nWarning: It\'ll disable if ' +
            u'the user input more than 2 files.'))

    args = parser.parse_args()

    if (len(argv) < 5):
        parser.print_usage()
        sys.exit(1)

    return args

def minify(template_string):
    u"""Minifies CSS, JavaScript and HTML for Django templates."""

    template_string = template_string.replace('\n', '')
    template_string = DJANGO_COMMENT_PATTERN.sub('', template_string)

    html = u''
    for fragment in TAGS_PATTERN.split(template_string):
        if fragment.startswith(STYLE_OPENING_TAG):
            html += minify_css(text=fragment)
        elif fragment.startswith(SCRIPT_OPENING_TAG):
            html += minify_js(text=fragment)
        else:
            html += fragment

    return html_minify(html, ignore_comments=False)

def keep_django_variables(function):
    u"""Keeps Django's variables by it owns notation, double braces.

    Stores current Django variables to a map, then restores them before exiting.

    """

    def wrapper(*args, **kwargs):
        if 'text' not in kwargs:
            kwargs['text'] = u''

        # Store Django variables.
        django_variables = DJANGO_VARIABLE_PATTERN.findall(kwargs['text'])
        temp_variables = [generate_random_string(10) for _ in xrange(len(django_variables))]
        LOGGER.info(u'List Django variables:')
        for index, django_variable in enumerate(django_variables):
            kwargs['text'] = kwargs['text'].replace(django_variable, temp_variables[index])

            LOGGER.info(django_variable)

        minified_text = function(*args, **kwargs)

        # Restore Django variables.
        for index, temp_variable in enumerate(temp_variables):
            minified_text = minified_text.replace(temp_variable, django_variables[index])

        return minified_text

    return wrapper

def generate_random_string(length):
    u"""Generates a random string based on the length you specified.

    Examples:

        >>> len(generate_random_string(10))
        10

    """

    return ''.join(random.choice(string.ascii_letters) for _ in xrange(length))

@keep_django_variables
def minify_css(text=u''):
    u"""Minifies CSS of Django template."""

    scss_file_handler, scss_file = tempfile.mkstemp('.scss')
    css_file_handler, css_file = tempfile.mkstemp('.css')
    LOGGER.debug(u'scss_file: {}'.format(scss_file))

    minified_css = u''
    for bit in STYLE_PATTERN.split(text):
        LOGGER.debug(u'CSS bit: {}'.format(bit))

        if not bit:
            continue

        if bit.startswith('<'):
            minified_css += bit
            continue

        with open(scss_file, u'w') as f:
            f.write(bit)

        compress_scss_to_css(scss_file, css_file)

        with open(css_file, u'r') as f:
            compressed_css = f.read()

        minified_css += compressed_css.rstrip()

        os.close(scss_file_handler)
        os.close(css_file_handler)

    os.remove(scss_file)
    os.remove(css_file)

    return minified_css

def compress_scss_to_css(scss_file, css_file):
    u"""Compressing scss file to css file by Sass."""

    command = '`which sass` --style compressed {0}:{1}'.format(scss_file, css_file)
    popen = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = popen.communicate()
    if stderr:
        LOGGER.error(u'Popen Error: {}'.format(stderr))
        raise CSSMinifyError
    if stdout:
        LOGGER.info(u'Popen Out: {}'.format(stdout))

@keep_django_variables
def minify_js(text=u''):
    u"""Minifies JavaScript of Django template."""

    minified_js = u''
    for bit in SCRIPT_PATTERN.split(text):
        LOGGER.debug(u'JS bit: {}'.format(bit))

        if not bit:
            continue

        if bit.startswith('<'):
            minified_js += bit
            continue

        # Do not mangle top level variables, because other scripts inside HTML tags may invoke them.
        minified_js += slimit.minify(bit, mangle=True, mangle_toplevel=False)

    return minified_js


def main(argv=sys.argv[:]):
    u"""Main function"""

    args = get_arguments(argv)

    try:
        with open(args.input, u'r') as f:
            template_string = f.read()
    except IOError:
        sys.exit(u'The input file does not exists, {}.'.format(args.input))

    minified_string = minify(template_string)

    try:
        with open(args.output, u'w') as f:
            f.write(minified_string)
    except IOError:
        sys.exit(u'Output file failed. Please make sure the file path is valid.')

    return 0


if __name__ == '__main__':
    sys.exit(main())


# Refer to PEP8 http://www.python.org/dev/peps/pep-0008/
# vim: set hls is ai et sw=4 sts=4 ts=8 nu ft=python:
