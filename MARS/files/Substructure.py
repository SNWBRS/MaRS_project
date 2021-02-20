from CGRtools.CGRreactor import CGRreactor
from CGRtools.files.SDFrw import SDFread

db = SDFread(open('hasan.sdf')).read()
cgrr = CGRreactor()

def searcher(query, data):
    res = []
    for m in data:
        gm = cgrr.get_cgr_matcher(query, m)
        if gm.subgraph_is_isomorphic():
            res.append(m)

    return res

print(searcher(db[0], db))
