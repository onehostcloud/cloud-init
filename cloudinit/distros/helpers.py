# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Canonical Ltd.
#    Copyright (C) 2012 Yahoo! Inc.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

from StringIO import StringIO

from cloudinit import util


def _chop_comment(text, comment_chars):
    comment_locations = [text.find(c) for c in comment_chars]
    comment_locations = [c for c in comment_locations if c != -1]
    if not comment_locations:
        return (text, '')
    min_comment = min(comment_locations)
    before_comment = text[0:min_comment]
    comment = text[min_comment:]
    return (before_comment, comment)


# See: man hosts
# or http://unixhelp.ed.ac.uk/CGI/man-cgi?hosts
class HostsConf(object):
    def __init__(self, text):
        self._text = text
        self._contents = None

    def parse(self):
        if self._contents is None:
            self._contents = self._parse(self._text)

    def get_entry(self, ip):
        self.parse()
        options = []
        for (line_type, components) in self._contents:
            if line_type == 'option':
                (pieces, _tail) = components
                if len(pieces) and pieces[0] == ip:
                    options.append(pieces[1:])
        return options

    def del_entries(self, ip):
        self.parse()
        n_entries = []
        for (line_type, components) in self._contents:
            if line_type != 'option':
                n_entries.append((line_type, components))
                continue
            else:
                (pieces, _tail) = components
                if len(pieces) and pieces[0] == ip:
                    pass
                elif len(pieces):
                    n_entries.append((line_type, list(components)))
        self._contents = n_entries

    def add_entry(self, ip, canonical_hostname, *aliases):
        self.parse()
        self._contents.append(('option',
                              ([ip, canonical_hostname] + list(aliases), '')))

    def _parse(self, contents):
        entries = []
        for line in contents.splitlines():
            if not len(line.strip()):
                entries.append(('blank', [line]))
                continue
            (head, tail) = _chop_comment(line.strip(), '#')
            if not len(head):
                entries.append(('all_comment', [line]))
                continue
            entries.append(('option', [head.split(None), tail]))
        return entries

    def __str__(self):
        self.parse()
        contents = StringIO()
        for (line_type, components) in self._contents:
            if line_type == 'blank':
                contents.write("%s\n")
            elif line_type == 'all_comment':
                contents.write("%s\n" % (components[0]))
            elif line_type == 'option':
                (pieces, tail) = components
                pieces = [str(p) for p in pieces]
                pieces = "\t".join(pieces)
                contents.write("%s%s\n" % (pieces, tail))
        return contents.getvalue()


# See: man resolv.conf
class ResolvConf(object):
    def __init__(self, text):
        self._text = text
        self._contents = None

    def parse(self):
        if self._contents is None:
            self._contents = self._parse(self._text)

    @property
    def nameservers(self):
        self.parse()
        return self._retr_option('nameserver')

    @property
    def local_domain(self):
        self.parse()
        dm = self._retr_option('domain')
        if dm:
            return dm[0]
        return None

    @property
    def search_domains(self):
        self.parse()
        current_sds = self._retr_option('search')
        flat_sds = []
        for sdlist in current_sds:
            for sd in sdlist.split(None):
                if sd:
                    flat_sds.append(sd)
        return flat_sds

    def __str__(self):
        self.parse()
        contents = StringIO()
        for (line_type, components) in self._contents:
            if line_type == 'blank':
                contents.write("\n")
            elif line_type == 'all_comment':
                contents.write("%s\n" % (components[0]))
            elif line_type == 'option':
                (cfg_opt, cfg_value, comment_tail) = components
                line = "%s %s" % (cfg_opt, cfg_value)
                if len(comment_tail):
                    line += comment_tail
                contents.write("%s\n" % (line))
        return contents.getvalue()

    def _retr_option(self, opt_name):
        found = []
        for (line_type, components) in self._contents:
            if line_type == 'option':
                (cfg_opt, cfg_value, _comment_tail) = components
                if cfg_opt == opt_name:
                    found.append(cfg_value)
        return found

    def add_nameserver(self, ns):
        self.parse()
        current_ns = self._retr_option('nameserver')
        new_ns = list(current_ns)
        new_ns.append(str(ns))
        new_ns = util.uniq_list(new_ns)
        if len(new_ns) == len(current_ns):
            return current_ns
        if len(current_ns) >= 3:
            # Hard restriction on only 3 name servers
            raise ValueError(("Adding %r would go beyond the "
                              "'3' maximum name servers") % (ns))
        self._remove_option('nameserver')
        for n in new_ns:
            self._contents.append(('option', ['nameserver', n, '']))
        return new_ns

    def _remove_option(self, opt_name):

        def remove_opt(item):
            line_type, components = item
            if line_type != 'option':
                return False
            (cfg_opt, _cfg_value, _comment_tail) = components
            if cfg_opt != opt_name:
                return False
            return True

        new_contents = []
        for c in self._contents:
            if not remove_opt(c):
                new_contents.append(c)
        self._contents = new_contents

    def add_search_domain(self, search_domain):
        flat_sds = self.search_domains
        new_sds = list(flat_sds)
        new_sds.append(str(search_domain))
        new_sds = util.uniq_list(new_sds)
        if len(flat_sds) == len(new_sds):
            return new_sds
        if len(flat_sds) >= 6:
            # Hard restriction on only 6 search domains
            raise ValueError(("Adding %r would go beyond the "
                              "'6' maximum search domains") % (search_domain))
        s_list  = " ".join(new_sds)
        if len(s_list) > 256:
            # Some hard limit on 256 chars total
            raise ValueError(("Adding %r would go beyond the "
                              "256 maximum search list character limit")
                              % (search_domain))
        self._remove_option('search')
        self._contents.append(('option', ['search', s_list, '']))
        return flat_sds

    @local_domain.setter
    def local_domain(self, domain):
        self.parse()
        self._remove_option('domain')
        self._contents.append(('option', ['domain', str(domain), '']))
        return domain

    def _parse(self, contents):
        entries = []
        for (i, line) in enumerate(contents.splitlines()):
            sline = line.strip()
            if not sline:
                entries.append(('blank', [line]))
                continue
            (head, tail) = _chop_comment(line, ';#')
            if not len(head.strip()):
                entries.append(('all_comment', [line]))
                continue
            if not tail:
                tail = ''
            try:
                (cfg_opt, cfg_values) = head.split(None, 1)
            except (IndexError, ValueError):
                raise IOError("Incorrectly formatted resolv.conf line %s"
                              % (i + 1))
            if cfg_opt not in ['nameserver', 'domain',
                               'search', 'sortlist', 'options']:
                raise IOError("Unexpected resolv.conf option %s" % (cfg_opt))
            entries.append(("option", [cfg_opt, cfg_values, tail]))
        return entries


