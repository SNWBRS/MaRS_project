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
from .CGRreactor import CGRreactor
import networkx as nx
from networkx.algorithms import isomorphism as gis
from .files import MoleculeContainer, ReactionContainer


class CGRcore(object):
    def __init__(self, cgr_type='0', extralabels=False):

        self.__disstemplate = self.__disscenter()
        self.__cgrtype = self.__getcgrtype(cgr_type)
        self.__extralabels = extralabels
        self.__node_marks = [('s_%s' % mark, 'p_%s' % mark, 'sp_%s' % mark)
                             for mark in ('neighbors', 'hyb', 'stereo', 'charge')]
        self.__edge_marks = [('s_%s' % mark, 'p_%s' % mark, 'sp_%s' % mark) for mark in ('bond', 'stereo')]

    def getCGR(self, data):
        if self.__cgrtype in (1, 2, 3, 4, 5, 6):
            g = self.__reaction_splitter(data)
            if self.__extralabels:
                g = self.__setlabels(g)
        else:
            res = self.merge_mols(data)
            if self.__extralabels:
                res = dict(substrats=self.__setlabels(res['substrats']), products=self.__setlabels(res['products']))

            g = self.__compose(res)

        g.meta.update(data.meta)
        return g

    def dissCGR(self, g):
        tmp = ReactionContainer(meta=g.meta)
        for category, (edge, pattern) in self.__disstemplate.items():
            components, *_ = CGRreactor.getbondbrokengraph(g, pattern, gis.categorical_edge_match(edge, None))
            for mol in components:
                for n, m, edge_attr in mol.edges(data=True):
                    for i, j in self.__attrcompose['edges'][category].items():
                        if j in edge_attr:
                            mol[n][m][i] = edge_attr[j]
                for n, node_attr in mol.nodes(data=True):
                    for i, j in self.__attrcompose['nodes'][category].items():
                        if j in node_attr:
                            mol.node[n][i] = node_attr[j]
                tmp[category].append(mol)
        return tmp

    def __reaction_splitter(self, data):
        if self.__cgrtype == 1:
            g = nx.union_all(data.substrats)
        elif self.__cgrtype == 2:
            g = nx.union_all(data.products)
        elif self.__cgrtype == 3:
            g = nx.union_all(self.__getmols(data.substrats, self.__needed['substrats']))
        elif self.__cgrtype == 4:
            g = nx.union_all(self.__getmols(data.products, self.__needed['products']))
        elif self.__cgrtype == 5:
            g = nx.union_all(self.__excmols(data.substrats, self.__needed['substrats']))
        elif self.__cgrtype == 6:
            g = nx.union_all(self.__excmols(data.products, self.__needed['products']))
        else:
            raise Exception('Splitter Error')
        return g or MoleculeContainer()

    @staticmethod
    def __getmols(data, needed):
        mols = []
        for x in needed:
            try:
                mols.append(data[x])
            except IndexError:
                pass
        return mols

    @staticmethod
    def __excmols(data, needed):
        mols = data.copy()
        for x in needed:
            try:
                mols.pop(x)
            except IndexError:
                pass
        return mols

    def merge_mols(self, data):
        if self.__cgrtype == 0:
            substrats = nx.union_all(data.substrats)
            products = nx.union_all(data.products)

        elif self.__cgrtype == 7:
            substrats = nx.union_all(self.__getmols(data.substrats, self.__needed['substrats']))
            products = nx.union_all(self.__getmols(data.products, self.__needed['products']))
        elif self.__cgrtype == 8:
            substrats = nx.union_all(self.__excmols(data.substrats, self.__needed['substrats']))
            products = nx.union_all(self.__excmols(data.products, self.__needed['products']))
        elif self.__cgrtype == 9:
            substrats = nx.union_all(self.__excmols(data.substrats, self.__needed['substrats']))
            products = nx.union_all(self.__getmols(data.products, self.__needed['products']))
        elif self.__cgrtype == 10:
            substrats = nx.union_all(self.__getmols(data.substrats, self.__needed['substrats']))
            products = nx.union_all(self.__excmols(data.products, self.__needed['products']))
        else:
            raise Exception('Merging need reagents and products')

        return dict(substrats=substrats or MoleculeContainer(), products=products or MoleculeContainer())

    @staticmethod
    def __setlabels(g):
        for i in g.nodes():
            label = {'s_hyb': 1, 'p_hyb': 1, 'sp_hyb': 1, 's_neighbors': 0, 'p_neighbors': 0, 'sp_neighbors': 0}
            #  hyb 1- sp3; 2- sp2; 3- sp1; 4- aromatic
            for b, h, n in (('s_bond', 's_hyb', 's_neighbors'), ('p_bond', 'p_hyb', 'p_neighbors')):
                for node, bond in g[i].items():
                    if g.node[node]['element'] != 'H' and bond[b]:
                        label[n] += 1

                    if bond[b] in (1, None):
                        pass
                    elif bond[b] == 4:
                        label[h] = 4
                    elif bond[b] == 3 or (bond[b] == 2 and label[h] == 2):  # Если есть 3-я или две 2-х связи, то sp1
                        label[h] = 3
                    elif bond[b] == 2:  # Если есть 2-я связь, но до этого не было найдено другой 2-й, 3-й, или аром.
                        label[h] = 2
            for n, m, h in (('s_hyb', 'p_hyb', 'sp_hyb'), ('s_neighbors', 'p_neighbors', 'sp_neighbors')):
                label[h] = (label[n], label[m]) if label[n] != label[m] else label[n]

            for k in list(label):
                if g.node[i].get(k) is not None:
                    label.pop(k)

            g.node[i].update(label)
        return g

    @staticmethod
    def __attr_merge(attr_iter, marks):
        for attr in attr_iter:
            for s, p, sp in marks:
                ls = attr.get(s)
                lp = attr.get(p)

                if isinstance(ls, list) or isinstance(lp, list):
                    if isinstance(ls, list) and isinstance(lp, list):
                        if ls == lp:
                            attr[sp] = attr[s] = attr[p] = list(set(ls))
                            continue

                        attr[sp] = list(set((x, y) for x, y in zip(ls, lp) if x != y))
                    elif isinstance(ls, list):
                        attr[sp] = list(set((x, lp) for x in ls if x != lp))
                    else:
                        attr[sp] = list(set((ls, x) for x in lp if x != ls))

                    attr[s] = [x for x, _ in attr[sp]]
                    attr[p] = [x for _, x in attr[sp]]

                elif ls != lp:
                    attr[sp] = (ls, lp)
                elif ls is not None:
                    attr[sp] = ls
                else:
                    attr.pop(sp, None)

    def __compose(self, data):
        """ remove from union graphs of products or substrats data about substrats or products
        """
        common = set(data['substrats']).intersection(data['products'])
        products = data['products']
        substrats = data['substrats']
        extended_common = set()

        """ remove bond, stereo, neighbors and hybridization states for common atoms.
        """
        for i, g in (('substrats', substrats), ('products', products)):
            for n, m in g.edges(common):
                extended_common.update([n, m])
                for j in self.__popdict[i]['edge']:
                    g[n][m].pop(j, None)

            for n in common:
                for j in self.__popdict[i]['node']:
                    g.node[n].pop(j, None)

        """ remove neighbors and hybridization states for common frontier atoms.
        """
        bubble = extended_common.difference(common)
        for i, g in (('substrats', substrats), ('products', products)):
            for n in bubble.intersection(g):
                for j in self.__popdict[i]['ext_node']:
                    g.node[n].pop(j, None)

        """ compose graphs. kostyl
        """
        g = substrats
        g.add_nodes_from(products.nodes(data=True))
        g.add_edges_from(products.edges(data=True))

        """ remove edges without bonds
        """
        for n, m in g.edges(extended_common):
            if g[n][m].get('s_bond') == g[n][m].get('p_bond') is None:
                g.remove_edge(n, m)

        """ update sp_* marks
        """
        self.__attr_merge((g.node[n] for n in extended_common), self.__node_marks)
        self.__attr_merge((g[n][m] for n, m in g.edges(common)), self.__edge_marks)

        return g

    @staticmethod
    def __disscenter():
        g1 = nx.Graph()
        g2 = nx.Graph()

        g1.add_edges_from([(1, 2, dict(s_bond=None))])
        g2.add_edges_from([(1, 2, dict(p_bond=None))])
        return dict(substrats=('s_bond', [g1]), products=('p_bond', [g2]))

    def __getcgrtype(self, cgrtype):
        needed = [int(x) for x in cgrtype.split(',')]
        if needed[0] == 0:
            t = 0  # CGR
        elif needed[0] == 1:
            t = 1  # all reagents
        elif needed[0] == 2:
            t = 2  # all products
        elif not any(True for x in needed if -200 < x < -100) and not any(True for x in needed if -300 < x < -200) and \
                any(True for x in needed if 100 < x < 200) and any(True for x in needed if 200 < x < 300):
            t = 7  # CGR on included parts of reagents and products
        elif any(True for x in needed if -200 < x < -100) and any(True for x in needed if -300 < x < -200):
            t = 8  # CGR on excluded parts of reagents and products
        elif any(True for x in needed if -200 < x < -100) and not any(True for x in needed if -300 < x < -200) and \
                any(True for x in needed if 200 < x < 300):
            t = 9  # CGR on excluded part of reagents and included part of products
        elif not any(True for x in needed if -200 < x < -100) and any(True for x in needed if -300 < x < -200) and \
                any(True for x in needed if 100 < x < 200):
            t = 10  # CGR on excluded part of products and included part of reagents
        elif 100 < needed[0] < 200:
            t = 3  # only included part of reagents
        elif 200 < needed[0] < 300:
            t = 4  # only included part of products
        elif -200 < needed[0] < -100:
            t = 5  # only excluded part of reagents
        elif -300 < needed[0] < -200:
            t = 6  # only excluded part of products
        else:
            t = 0

        if t > 2:
            self.__needed = dict(substrats=sorted([abs(x) - 101 for x in needed if 100 < abs(x) < 200], reverse=True),
                                 products=sorted([abs(x) - 201 for x in needed if 200 < abs(x) < 300], reverse=True))
        return t

    __popdict = dict(products=dict(edge=('s_bond', 's_stereo'), node=('s_charge', 's_stereo', 's_neighbors', 's_hyb'),
                                   ext_node=('s_neighbors', 's_hyb')),
                     substrats=dict(edge=('p_bond', 'p_stereo'), node=('p_charge', 'p_stereo', 'p_neighbors', 'p_hyb'),
                                    ext_node=('p_neighbors', 'p_hyb')))

    __attrcompose = dict(edges=dict(substrats=dict(p_bond='s_bond', p_stereo='s_stereo'),
                                    products=dict(s_bond='p_bond', s_stereo='p_stereo')),
                         nodes=dict(substrats=dict(p_charge='s_charge', p_stereo='s_stereo',
                                                   p_neighbors='s_neighbors', p_hyb='s_hyb'),
                                    products=dict(s_charge='p_charge', s_stereo='p_stereo',
                                                  s_neighbors='p_neighbors', s_hyb='p_hyb')))
