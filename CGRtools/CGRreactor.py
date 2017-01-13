# -*- coding: utf-8 -*-
#
# Copyright 2014-2016 Ramil Nugmanov <stsouko@live.ru>
# This file is part of cgrtools.
#
# cgrtools is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#
import networkx as nx
import operator
from itertools import product, combinations
from networkx.algorithms import isomorphism as gis
from .FEAR import FEAR
from .files.RDFrw import RDFread


def patcher(matrix):
    """ remove edges bw common nodes. add edges from template and replace nodes data
    :param matrix: dict
    """
    s = matrix['substrats'].copy()
    p = matrix['products'].copy()

    common = set(p).intersection(s)
    for i in common:
        for j in {'s_charge', 's_hyb', 's_neighbors', 's_stereo',
                  'p_charge', 'p_hyb', 'p_neighbors', 'p_stereo'}.intersection(p.node[i]):
            if isinstance(p.node[i][j], dict):
                p.node[i][j] = p.node[i][j][s.node[i][j]]

    for m, n, a in p.edges(data=True):
        if m in common and n in common:
            for j in {'s_bond', 'p_bond', 's_stereo', 'p_stereo'}.intersection(a):
                if isinstance(a[j], dict):
                    a[j] = a[j][s.edge[m][n][j]]

    s.remove_edges_from(combinations(common, 2))

    return nx.compose(s, p)


def list_eq(a, b):
    return True if b is None else a in b if isinstance(b, list) else a == b


def simple_eq(a, b):
    return True if b is None else a == b


class CGRreactor(object):
    def __init__(self, stereo=False, hyb=False, neighbors=False, isotop=False, element=True, deep=0):
        self.__rctemplate = self.__reactioncenter()
        self.__stereo = stereo
        self.__isotop = isotop
        self.__hyb = hyb
        self.__neighbors = neighbors
        self.__element = element
        self.__deep = deep

        stereo_match = (['sp_stereo'], [None], [list_eq]) if stereo else ([], [], [])
        pstereo_match = (['p_stereo'], [None], [operator.eq]) if stereo else ([], [], [])

        hyb_match = (['sp_hyb'], [None],
                     [list_eq]) if hyb else ([], [], [])

        neig_match = (['sp_neighbors'], [None],
                      [list_eq]) if neighbors else ([], [], [])

        self.__node_match = gis.generic_node_match(['isotop', 'sp_charge', 'element'] +
                                                   stereo_match[0] + neig_match[0] + hyb_match[0],
                                                   [None] * 3 + stereo_match[1] + neig_match[1] + hyb_match[1],
                                                   [list_eq] * 3 +
                                                   stereo_match[2] + neig_match[2] + hyb_match[2])

        self.__edge_match = gis.generic_node_match(['sp_bond'] + stereo_match[0],
                                                   [None] + stereo_match[1],
                                                   [list_eq] + stereo_match[2])

        self.__node_match_products = gis.categorical_node_match(['element', 'isotop', 'p_charge'] + pstereo_match[0],
                                                                [None] * 3 + pstereo_match[1])

        self.__edge_match_products = gis.categorical_edge_match(['p_bond'] + pstereo_match[0],
                                                                [None] + pstereo_match[1])

        self.__edge_match_only_bond = gis.categorical_edge_match(['s_bond', 'p_bond'], [None] * 2)

    @staticmethod
    def __reactioncenter():
        g1 = nx.Graph()
        g2 = nx.Graph()
        g1.add_edges_from([(1, 2, dict(s_bond=1, p_bond=None)), (2, 3, dict(s_bond=None, p_bond=1))])
        g2.add_edges_from([(1, 2, dict(s_bond=None, p_bond=1))])
        return [g1, g2]

    def get_cgr_matcher(self, g, h):
        return gis.GraphMatcher(g, h, node_match=self.__node_match, edge_match=self.__edge_match)

    def get_template_searcher(self, templates, patch=True, speed=False):
        if speed:
            _fear = FEAR(isotop=self.__isotop, stereo=self.__stereo, hyb=self.__hyb,
                         element=self.__element, deep=self.__deep)
            _fear.sethashlib([x['meta'] for x in templates])
            templates = {x['meta']['CGR_FEAR_SHASH']: x for x in templates}

        def searcher(g):
            hitlist = []
            if speed or not patch:
                hit, hitlist, _ = _fear.chkreaction(g, full=(not patch))
                if not patch:
                    return hit
            for i in ((templates[x[2]] for x in hitlist) if speed else templates):
                gm = self.get_cgr_matcher(g, i['substrats'])
                for j in gm.subgraph_isomorphisms_iter():
                    res = dict(substrats=g, meta=i['meta'],
                               products=self.__remapgroup(i['products'], g,  {y: x for x, y in j.items()})[0])
                    yield res

        return searcher

    @staticmethod
    def getbondbrokengraph(g, rc_templates, edge_match):
        g = g.copy()
        lose_bonds = {}
        for i in rc_templates:
            gm = gis.GraphMatcher(g, i, edge_match=edge_match)
            for j in gm.subgraph_isomorphisms_iter():
                mapping = {y: x for x, y in j.items()}
                if 3 in mapping:
                    lose_bonds[(mapping[2], mapping[1])] = g[mapping[1]][mapping[2]]
                    g.remove_edge(mapping[2], mapping[3])
                    g.remove_edge(mapping[1], mapping[2])
                elif not any(nx.has_path(g, *x) for x in product((y for x in lose_bonds for y in x), mapping.values())):
                    # запилить проверку связности атомов 1 или 2 с lose_map атомами
                    g.remove_edge(mapping[1], mapping[2])
        components = list(nx.connected_component_subgraphs(g))
        return components, lose_bonds

    def clonesubgraphs(self, g):
        r_group = []
        x_group = {}
        r_group_clones = []
        newcomponents = []

        ''' search bond breaks and creations
        '''
        components, lose_bonds = self.getbondbrokengraph(g, self.__rctemplate, self.__edge_match_only_bond)
        lose_map = {x: y for x, y in lose_bonds}
        ''' extract subgraphs and sort by group type (R or X)
        '''
        x_terminals = set(lose_map.values())
        r_terminals = set(lose_map)

        for i in components:
            x_terminal_atom = x_terminals.intersection(i)
            r_terminal_atom = r_terminals.intersection(i)

            if x_terminal_atom:
                x_group[x_terminal_atom.pop()] = i
            elif r_terminal_atom:
                r_group.append([r_terminal_atom, i])
            else:
                newcomponents.append(i)
        ''' search similar R groups and patch.
        '''
        tmp = g.copy()
        for i in newcomponents:
            for k, j in r_group:
                gm = gis.GraphMatcher(j, i, node_match=self.__node_match_products,
                                      edge_match=self.__edge_match_products)
                ''' search for similar R-groups started from bond breaks.
                '''
                mapping = next((x for x in gm.subgraph_isomorphisms_iter() if k.intersection(x)), None)
                if mapping:
                    r_group_clones.append([k, mapping])
                    tmp = nx.compose(tmp, self.__remapgroup(j, tmp, mapping)[0])
                    break
        ''' add lose X groups to R groups
        '''
        for i, j in r_group_clones:
            for k in i:
                remappedgroup, mapping = self.__remapgroup(x_group[lose_map[k]], tmp, {})
                tmp = nx.union(tmp, remappedgroup)
                tmp.add_edge(j[k], mapping[lose_map[k]], **lose_bonds[(k, lose_map[k])])

        return tmp

    @staticmethod
    def __remapgroup(g, h, mapping):
        newmap = mapping.copy()
        newmap.update({x: y for x, y in zip(set(g).difference(newmap), set(range(1, 1000)).difference(h))})
        return nx.relabel_nodes(g, newmap), newmap

    @staticmethod
    def get_templates(templates):
        _templates = []
        if templates:
            source = RDFread(templates)

            for template in source:
                matrix = dict(meta=template['meta'])
                for i in ('products', 'substrats'):
                    x = nx.union_all(template[i])
                    matrix[i] = x

                common = set(matrix['products']).intersection(matrix['substrats'])
                for n in common:
                    for j in {'s_charge', 's_hyb', 's_neighbors', 's_stereo',
                              'p_charge', 'p_hyb', 'p_neighbors', 'p_stereo'}.intersection(matrix['products'].node[n]):
                        if isinstance(matrix['products'].node[n][j], list):
                            matrix['products'].node[n][j] = {x: y for x, y in zip(matrix['substrats'].node[n][j],
                                                                                  matrix['products'].node[n][j])}
                for m, n, a in matrix['products'].edges(data=True):
                    if m in common and n in common:
                        for j in {'s_bond', 'p_bond', 's_stereo', 'p_stereo'}.intersection(a):
                            if isinstance(a[j], list):
                                matrix['products'].edge[m][n][j] = {x: y for x, y in
                                                                    zip(matrix['substrats'].edge[m][n][j], a[j])}

                nx.relabel_nodes(matrix['substrats'], {x: x + 1000 for x in matrix['substrats']}, copy=False)
                nx.relabel_nodes(matrix['products'], {x: x + 1000 for x in matrix['products']}, copy=False)

                _templates.append(matrix)
        return _templates
