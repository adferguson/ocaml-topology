#!/usr/bin/python

'''this file generates an AB fat tree in dot notation with few assumptions:
1) fan out is multiple of 2
2) all switches have same incoming and outgoing edges, except the root nodes
3) all switches have same fan out '''

'''
{rank = same; "s17"; "s18"; "s19"; "s20"; }
{rank = same; "s9"; "s10"; "s11"; "s12"; "s13"; "s14"; "s15"; "s16"; }
{rank = same; "s1"; "s2"; "s3"; "s4"; "s5"; "s6"; "s7"; "s8"; }
{rank = same; "h1"; "h2"; "h3"; "h4"; "h5"; "h6"; "h7"; "h8"; "h9"; "h10"; "h11"; "h12"; "h13"; "h14"; "h15"; "h16"; }
'''

import sys
import argparse
import pprint
import string
import networkx as nx
from mininet.util import macColonHex, ipAdd

def generate(fanout,depth):
    L = depth - 1
    p = fanout / 2
    switches = ['s'+ str(i) for i in range(1, ((2*L + 1) * (p ** L)+1))]
    hosts = ['h' + str(i) for i in range(1, 2 * (p ** (L+1)) + 1)]
    nodes = switches + hosts
    graph = nx.DiGraph()
    for node in switches:
        graph.add_node(node, type='switch', id=int(node[1:]))
    for node in hosts:
        graph.add_node(node, type='host',
            id=int(node[1:]),
            mac=macColonHex( int(node[1:]) ),
            ip=ipAdd( int(node[1:]) ) )


    graph.switches = switches
    graph.hosts = hosts
    graph.p = p
    graph.L = L
    n = len(switches)
    nc = p**L
    graph.core_switches = switches[(n-nc):]
    ne = 2*p**L
    graph.edge_switches = switches[0:ne]
    graph.agg_switches = switches[ne:(n-nc)]
    assert len(graph.core_switches) + len(graph.edge_switches) + len(graph.agg_switches) == len(switches)

    for idx in range(2 * (p ** (depth-1))):
        node = nodes[idx]
        c = 1
        for j in range(idx*p, idx*p + p):
            hostnode = hosts[j]
            graph.add_edge(hostnode, node,
                attr_dict={'sport':1,'dport':c,'capacity':'1Gbps','cost':'1'})
            graph.add_edge(node, hostnode,
                attr_dict={'sport':c,'dport':1,'capacity':'1Gbps','cost':'1'})
            #print "dport: %d" % (c)
            c += 1

    for i in range(L):
        groups = 2*(p ** (L - i))
        for g in range(groups):
            '''type A = 0; type B = 1'''
            sttype = g % 2
            for j in range(p ** i):
                idx = i * 2 * (p ** L) + g * (p ** i) + j
                #print "i, g, j, idx, sstype: %d %d %d %d %d" % (i, g, j, idx, sttype)
                node = nodes[idx]
                if i < L - 1:
                    parentsg = g / p
                else:
                    parentsg = 0
                parentbase = (i + 1) * 2 * (p ** L) + parentsg * (p ** (i + 1))
                #print "parentbase: %d" % (parentbase)
                if sttype == 0:
                    parentbase = parentbase + j * p
                    parentsidxs = range(parentbase, parentbase + p)
                else:
                    parentsidxs = [parentbase + j + x * (p ** i) for x in range(0, p)]
                #print parentsidxs
                c = 1
                assert len(parentsidxs) == p
                for pidx in parentsidxs:
                    parentnode = nodes[pidx]
                    sport = p + c
                    c += 1
                    if i < L - 1:
                        dport = (g % p) + 1
                    else:
                        dport = g + 1
                    assert sport <= 2*p
                    assert dport <= 2*p
                    #print "dport: %d" % (dport)
                    graph.add_edge(node, parentnode,
                        attr_dict={'sport':sport,'dport':dport,'capacity':'1Gbps','cost':'1'})
                    graph.add_edge(parentnode, node,
                        attr_dict={'sport':dport,'dport':sport,'capacity':'1Gbps','cost':'1'})
    return graph

def rec_routing_downwards(graph, node, host, level):
    upwards = [x for x in graph.neighbors_iter(node) if (x not in graph.hosts and graph.node[x]['level'] == level)]
    for upnode in upwards:
        e = graph.get_edge_data(node, upnode)
        graph.node[upnode]['routes'][host] = e['dport']
        if level+1 <= graph.L:
            rec_routing_downwards(graph, upnode, host, level+1)

def routing_upwards(graph, node):
    # by convention, port > p is facing upwards except for level L
    for port in range(1, graph.p+1):
        graph.node[node]['routes'][port] = graph.p + port

def to_netkat_set_of_tables_for_switches(graph, switches, withTopo=True):
    policy = []
    edge_policy = []
    for node in switches:
        table = []
        edge_table = []
        flt = "filter switch = %d" % (graph.node[node]['id'])
        #pprint.pprint(graph.node[node]['routes'])
        for k, v in graph.node[node]['routes'].iteritems():
            if k in graph.hosts:
                s = string.join((flt, "ethDst = %s" % (graph.node[k]['mac'])), " and ")
                s = string.join((s, "port := %d" % (v)), "; ")
                if graph.node[node]['level'] == 0:
                    edge_table.append(s)
                else:
                    table.append(s)
            else:
                hosts = find_all_hosts_below(graph, node)
                fltouthosts = string.join(map(lambda x: "not ethDst = %s" % (graph.node[x]['mac']), hosts), " and ")
                s = string.join((flt, "port = %d" % (k), fltouthosts), " and ")
                s = string.join((s, "port := %d" % (v)), "; ")
                table.append(s)
        #pprint.pprint(table)
        policy.extend(table)
        edge_policy.extend(edge_table)

    if withTopo:
        topo = []
        for src, dst, ed in graph.edges_iter(data=True):
            if src in graph.hosts or dst in graph.hosts:
                continue
            if src in switches or dst in switches:
                topoterm = "%s@%d => %s@%d" % (graph.node[src]['id'], ed['sport'], graph.node[dst]['id'], ed['dport'])
                topo.append(topoterm)

        edge_topo = []
        for host in graph.hosts:
            dst = graph.neighbors(host)[0]
            if dst in switches:
                ed = graph.get_edge_data(host, dst)
                topoterm = "%s@%d => 0@%d" % (graph.node[dst]['id'], ed['dport'], graph.node[host]['id'])
                edge_topo.append(topoterm)

        return "((\n%s\n);\n(\n%s\n))*;\n((\n%s\n);\n(\n%s\n))" % \
            (string.join(policy, " |\n"), string.join(topo, " |\n"),
             string.join(edge_policy, " |\n"), string.join(edge_topo, " |\n"))
    else:
        policy.extend(edge_policy)
        return "%s\n" % (string.join(policy, " |\n"))

def to_netkat_set_of_tables(graph, withTopo=True):
    return to_netkat_set_of_tables_for_switches(graph, graph.switches, withTopo) 

def to_netkat_test_set_of_tables(graph, withTopo=True):
    return to_netkat_set_of_tables_for_switches(graph, (graph.switches[0], graph.switches[1], graph.switches[8], graph.switches[9]), withTopo) 

def to_netkat_set_of_tables_failover_for_switches(graph, switches, withTopo=True, specializeInPort=True):
    policy = []
    edge_policy = []
    # edge
    for node in graph.edge_switches:
        if not node in switches:
            continue
        table = []
        edge_table = []
        flt = "filter switch = %d" % (graph.node[node]['id'])
        #pprint.pprint(graph.node[node]['routes'])
        for k, v in graph.node[node]['routes'].iteritems():
            if k in graph.hosts:
                s = string.join((flt, "ethDst = %s" % (graph.node[k]['mac'])), " and ")
                s = string.join((s, "port := %d" % (v)), "; ")
                if graph.node[node]['level'] == 0:
                    edge_table.append(s)
                else:
                    table.append(s)
            else:
                hosts = find_all_hosts_below(graph, node)
                fltouthosts = string.join(map(lambda x: "not ethDst = %s" % (graph.node[x]['mac']), hosts), " and ")
                s = string.join((flt, "port = %d" % (k), fltouthosts), " and ")
                v2 = ((v - graph.p) % graph.p) + 1 + graph.p
                s = string.join((s, "(port := %d + port := %d)" % (v, v2)), "; ")
                table.append(s)
        #pprint.pprint(table)
        policy.extend(table)
        edge_policy.extend(edge_table)

    # agg
    for node in graph.agg_switches:
        if not node in switches:
            continue
        table = []
        flt = "filter switch = %d" % (graph.node[node]['id'])
        #pprint.pprint(graph.node[node]['routes'])
        for k, v in graph.node[node]['routes'].iteritems():
            if k in graph.hosts:
                assert v <= graph.p

                if specializeInPort:
                    for port in range(1, graph.p*2+1):
                        if v == port:
                            continue
                        s = string.join((flt, "port = %d" % (port), "ethDst = %s" % (graph.node[k]['mac'])), " and ")
                        v2 = (v % graph.p) + 1
                        s = string.join((s, "(port := %d + port := %d)" % (v, v2)), "; ")
                        table.append(s)
                else:
                    s = string.join((flt, "ethDst = %s" % (graph.node[k]['mac'])), " and ")
                    v2 = (v % graph.p) + 1
                    s = string.join((s, "(port := %d + port := %d)" % (v, v2)), "; ")
                    table.append(s)

                #print v2
                reroute = (find_next_node(graph, node, v2))[0]
                #print reroute
                ed = graph.get_edge_data(node, reroute)
                inport = ed['dport']

                nextagg = find_next_sibling_node(graph, reroute, node)
                #print nextagg
                ed = graph.get_edge_data(reroute, nextagg)
                outport = ed['sport']

                s = string.join(("filter switch = %d" % (graph.node[reroute]['id']), "port = %d" % (inport),
                        "ethDst = %s" % (graph.node[k]['mac'])), " and ")
                s = string.join((s, "port := %d" % (outport)), "; ")
                table.append(s)
            else:
                hosts = find_all_hosts_below(graph, node)
                fltouthosts = string.join(map(lambda x: "not ethDst = %s" % (graph.node[x]['mac']), hosts), " and ")
                s = string.join((flt, "port = %d" % (k), fltouthosts), " and ")
                v2 = ((v - graph.p) % graph.p) + 1 + graph.p
                s = string.join((s, "(port := %d + port := %d)" % (v, v2)), "; ")
                table.append(s)

        #pprint.pprint(table)
        policy.extend(table)

    # core
    for node in graph.core_switches:
        if not node in switches:
            continue
        table = []
        flt = "filter switch = %d" % (graph.node[node]['id'])
        #pprint.pprint(graph.node[node]['routes'])
        for k, v in graph.node[node]['routes'].iteritems():
            assert k in graph.hosts

            if specializeInPort:
                for port in range(1, graph.p*2+1):
                    if v == port:
                        continue
                    s = string.join((flt, "port = %d" % (port), "ethDst = %s" % (graph.node[k]['mac'])), " and ")
                    v2 = (v % (2 * graph.p)) + 1
                    s = string.join((s, "(port := %d + port := %d)" % (v, v2)), "; ")
                    table.append(s)
            else:
                s = string.join((flt, "ethDst = %s" % (graph.node[k]['mac'])), " and ")
                v2 = (v % (2 * graph.p)) + 1
                s = string.join((s, "(port := %d + port := %d)" % (v, v2)), "; ")
                table.append(s)

            #print v2
            reroute = (find_next_node(graph, node, v2))[0]
            #print reroute
            ed = graph.get_edge_data(node, reroute)
            inport = ed['dport']

            nextcore = find_next_sibling_node(graph, reroute, node)
            #print nextcore
            ed = graph.get_edge_data(reroute, nextcore)
            outport = ed['sport']

            s = string.join(("filter switch = %d" % (graph.node[reroute]['id']), "port = %d" % (inport),
                    "ethDst = %s" % (graph.node[k]['mac'])), " and ")
            s = string.join((s, "port := %d" % (outport)), "; ")
            table.append(s)
        #pprint.pprint(table)
        policy.extend(table)

    if withTopo:
        topo = []
        for src, dst, ed in graph.edges_iter(data=True):
            if src in graph.hosts or dst in graph.hosts:
                continue
            if src in switches or dst in switches:
                topoterm = "%s@%d => %s@%d" % (graph.node[src]['id'], ed['sport'], graph.node[dst]['id'], ed['dport'])
                topo.append(topoterm)

        edge_topo = []
        for host in graph.hosts:
            dst = graph.neighbors(host)[0]
            if dst in switches:
                ed = graph.get_edge_data(host, dst)
                topoterm = "%s@%d => 0@%d" % (graph.node[dst]['id'], ed['dport'], graph.node[host]['id'])
                edge_topo.append(topoterm)

        return "((\n%s\n);\n(\n%s\n))*;\n((\n%s\n);\n(\n%s\n))" % \
            (string.join(map(lambda x: "(%s)" % (x), policy), " |\n"), string.join(topo, " |\n"), 
             string.join(edge_policy, " |\n"), string.join(edge_topo, " |\n"))
    else:
        policy.extend(edge_policy)
        return "%s\n" % (string.join(map(lambda x: "(%s)" % (x), policy), " |\n"))

def to_netkat_set_of_tables_failover(graph, withTopo=True):
    return to_netkat_set_of_tables_failover_for_switches(graph, graph.switches, withTopo) 

def to_netkat_test_set_of_tables_failover(graph, withTopo=True):
    return to_netkat_set_of_tables_failover_for_switches(graph, (graph.switches[0], graph.switches[1], graph.switches[8], graph.switches[9]), withTopo)

def find_next_sibling_node(graph, node, src):
    for k in graph.neighbors_iter(node):
        if k in graph.switches and graph.node[k]['level'] == graph.node[src]['level'] and k != src:
            return k

def find_next_node(graph, node, outport):
    #print "find_next_node", node, outport
    for src, dst, ed in graph.edges_iter([node], data=True):
        assert src == node
        if graph.node[dst]['type'] == 'host':
            continue
        if ed['sport'] == outport:
            return (dst, ed['dport'])

def find_host(graph, node, outport):
    for src, dst, ed in graph.edges_iter([node], data=True):
        assert src == node
        if graph.node[dst]['type'] != 'host':
            continue
        if ed['sport'] == outport:
            return dst

def find_all_hosts_below(graph, node):
    hosts = []
    for k in graph.neighbors_iter(node):
        if graph.node[k]['type'] == 'host':
            hosts.append(k)
        if k in graph.switches and graph.node[k]['level'] < graph.node[node]['level']:
            hosts.extend(find_all_hosts_below(graph, k))
    return hosts

def rec_set_of_paths_next_hop(graph, node, inport, dst, srchost, dsthost, switches):
    path = []
    flt = "filter switch = %d" % (graph.node[node]['id'])
    switches.add(node)
    if node == dst:
        assert dsthost in graph.node[dst]['routes']

    if dsthost in graph.node[node]['routes']:
        v = graph.node[node]['routes'][dsthost]
        path = [string.join((flt, "port := %d" % (v)), "; ")]
        if node == dst:
            return ([], path[0])
    else:
        assert inport in graph.node[node]['routes']
        #print "inport", inport
        v = graph.node[node]['routes'][inport]
        path = [string.join((flt, "port := %d" % (v)), "; ")]

    nextnode, nextinport = find_next_node(graph, node, v)
    #print "next", nextnode, nextinport
    p, edge = rec_set_of_paths_next_hop(graph, nextnode, nextinport, dst, srchost, dsthost, switches)
    path.extend(p)
    return path, edge

def to_netkat_set_of_paths_for_hosts(graph, hosts, withTopo=True):
    policy = []
    edge_policy = []
    switches = set()
    for srchost in hosts:
        src = graph.neighbors(srchost)[0]
        nextnode, inport = find_next_node(graph, srchost, 1)
        assert src == nextnode
        for dsthost in hosts:
            if srchost == dsthost:
                continue
            dst = graph.neighbors(dsthost)[0]
            flt = "filter ethSrc = %s; filter ethDst = %s" % (graph.node[srchost]['mac'], graph.node[dsthost]['mac'])
            #print "path", srchost, dsthost
            path, edge = rec_set_of_paths_next_hop(graph, src, inport, dst, srchost, dsthost, switches)
            #print string.join(path, " | ")
            if len(path) > 0:
                policy.append("(%s; ( %s ))" % (flt, string.join(path, " | ")))
            edge_policy.append("(%s; %s)" % (flt, edge))
            switches.add(src)
            switches.add(dst)

    if withTopo:
        topo = []
        for src, dst, ed in graph.edges_iter(data=True):
            if src in graph.hosts or dst in graph.hosts:
                continue
            if src not in switches or dst not in switches:
                continue
            topoterm = "%s@%d => %s@%d" % (graph.node[src]['id'], ed['sport'], graph.node[dst]['id'], ed['dport'])
            topo.append(topoterm)
        if len(topo) == 0:
            topo = ["id"]

        edge_topo = []
        for host in graph.hosts:
            dst = graph.neighbors(host)[0]
            if dst in switches:
                ed = graph.get_edge_data(host, dst)
                topoterm = "%s@%d => 0@%d" % (graph.node[dst]['id'], ed['dport'], graph.node[host]['id'])
                edge_topo.append(topoterm)

        return "((\n%s\n);\n(\n%s\n))*;\n((\n%s\n);\n(\n%s\n))" % \
                (string.join(policy, " |\n"), string.join(topo, " |\n"),
                 string.join(edge_policy, " |\n"), string.join(edge_topo, " |\n"))
    else:
        policy.extend(edge_policy)
        return "%s\n" % (string.join(policy, " |\n"))

def to_netkat_set_of_paths(graph, withTopo):
    return to_netkat_set_of_paths_for_hosts(graph, graph.hosts, withTopo=withTopo)

def to_netkat_test_set_of_paths(graph, withTopo):
    return to_netkat_set_of_paths_for_hosts(graph, graph.hosts[0:2], withTopo=withTopo)

def to_netkat_test_set_of_paths2(graph, withTopo):
    return to_netkat_set_of_paths_for_hosts(graph, [graph.hosts[0], graph.hosts[3]], withTopo=withTopo)

#########
#REAL_PATHS
#########
def rec_real_paths_next_hop(graph, node, inport, dst, srchost, dsthost, switches):
    path = []
    flt = "filter switch = %d" % (graph.node[node]['id'])
    switches.add(node)
    if node == dst:
        return []

    if dsthost in graph.node[node]['routes']:
        v = graph.node[node]['routes'][dsthost]
        s = string.join((flt, "port := %d" % (v)), "; ")
    else:
        assert inport in graph.node[node]['routes']
        #print "inport", inport
        v = graph.node[node]['routes'][inport]
        s = string.join((flt, "port := %d" % (v)), "; ")

    nextnode, nextinport = find_next_node(graph, node, v)
    ed = graph.get_edge_data(node, nextnode)
    topoterm = "%s@%d => %d@%d" % (graph.node[node]['id'], v, graph.node[nextnode]['id'], ed['dport'])
    path = [s + "; " + topoterm]
    #print "next", nextnode, nextinport
    if nextnode != dst:
        p = rec_real_paths_next_hop(graph, nextnode, nextinport, dst, srchost, dsthost, switches)
        path.extend(p)
    return path

def to_netkat_real_paths_for_hosts(graph, hosts, withTopo=True):
    policy = ["id"]
    edge_policy = []
    switches = set()
    for srchost in hosts:
        src = graph.neighbors(srchost)[0]
        nextnode, inport = find_next_node(graph, srchost, 1)
        assert src == nextnode
        for dsthost in hosts:
            if srchost == dsthost:
                continue
            dst = graph.neighbors(dsthost)[0]
            flt = "filter ethSrc = %s; filter ethDst = %s" % (graph.node[srchost]['mac'], graph.node[dsthost]['mac'])
            #print "path", srchost, dsthost
            path = rec_real_paths_next_hop(graph, src, inport, dst, srchost, dsthost, switches)
            #print string.join(path, " | ")
            if len(path) > 0:
                policy.append("(%s; %s)" % (flt, string.join(path, "; ")))
            switches.add(src)
            switches.add(dst)

    # edge
    for node in graph.edge_switches:
        edge_table = []
        flt = "filter switch = %d" % (graph.node[node]['id'])
        #pprint.pprint(graph.node[node]['routes'])
        for k, v in graph.node[node]['routes'].iteritems():
            if k in graph.hosts:
                s = string.join((flt, "filter ethDst = %s" % (graph.node[k]['mac']), "port := %d" % (v)), "; ")
                edge_table.append(s)
        edge_policy.extend(edge_table)

    if withTopo:
        edge_topo = []
        for host in graph.hosts:
            dst = graph.neighbors(host)[0]
            if dst in switches:
                ed = graph.get_edge_data(host, dst)
                topoterm = "%s@%d => 0@%d" % (graph.node[dst]['id'], ed['dport'], graph.node[host]['id'])
                edge_topo.append(topoterm)

        return "(\n%s\n);\n((\n%s\n);\n(\n%s\n))" % \
                (string.join(policy, " |\n"),
                 string.join(edge_policy, " |\n"), string.join(edge_topo, " |\n"))
    else:
        policy.extend(edge_policy)
        return "%s\n" % (string.join(policy, " |\n"))

def to_netkat_real_paths(graph, withTopo):
    return to_netkat_real_paths_for_hosts(graph, graph.hosts, withTopo=withTopo)

def to_netkat_test_real_paths(graph, withTopo):
    return to_netkat_real_paths_for_hosts(graph, graph.hosts[0:2], withTopo=withTopo)

def to_netkat_test_real_paths2(graph, withTopo):
    return to_netkat_real_paths_for_hosts(graph, [graph.hosts[0], graph.hosts[3]], withTopo=withTopo)

#########
#REAL_PATHS_NO_ID
#########
def rec_realnoid_paths_next_hop(graph, node, inport, dst, srchost, dsthost, switches):
    path = []
    flt = "filter switch = %d" % (graph.node[node]['id'])
    switches.add(node)
    if node == dst:
        assert dsthost in graph.node[dst]['routes']

    if dsthost in graph.node[node]['routes']:
        v = graph.node[node]['routes'][dsthost]
        s = string.join((flt, "port := %d" % (v)), "; ")
        if node == dst:
            topoterm = "%s@%d => 0@%d" % (graph.node[node]['id'], v, graph.node[dsthost]['id'])
            return [s + "; " + topoterm]
    else:
        assert inport in graph.node[node]['routes']
        #print "inport", inport
        v = graph.node[node]['routes'][inport]
        s = string.join((flt, "port := %d" % (v)), "; ")

    nextnode, nextinport = find_next_node(graph, node, v)
    ed = graph.get_edge_data(node, nextnode)
    topoterm = "%s@%d => %d@%d" % (graph.node[node]['id'], v, graph.node[nextnode]['id'], ed['dport'])
    path = [s + "; " + topoterm]
    #print "next", nextnode, nextinport
    p = rec_realnoid_paths_next_hop(graph, nextnode, nextinport, dst, srchost, dsthost, switches)
    path.extend(p)
    return path

def to_netkat_realnoid_paths_for_hosts(graph, hosts, withTopo=True):
    policy = []
    switches = set()
    for srchost in hosts:
        src = graph.neighbors(srchost)[0]
        nextnode, inport = find_next_node(graph, srchost, 1)
        assert src == nextnode
        for dsthost in hosts:
            if srchost == dsthost:
                continue
            dst = graph.neighbors(dsthost)[0]
            flt = "filter ethSrc = %s; filter ethDst = %s" % (graph.node[srchost]['mac'], graph.node[dsthost]['mac'])
            #print "path", srchost, dsthost
            path = rec_realnoid_paths_next_hop(graph, src, inport, dst, srchost, dsthost, switches)
            #print string.join(path, " | ")
            if len(path) > 0:
                policy.append("(%s; %s)" % (flt, string.join(path, "; ")))
            switches.add(src)
            switches.add(dst)

    return "%s\n" % (string.join(policy, " |\n"))

def to_netkat_realnoid_paths(graph, withTopo):
    return to_netkat_realnoid_paths_for_hosts(graph, graph.hosts, withTopo=withTopo)

def to_netkat_test_realnoid_paths(graph, withTopo):
    return to_netkat_realnoid_paths_for_hosts(graph, graph.hosts[0:2], withTopo=withTopo)

def to_netkat_test_realnoid_paths2(graph, withTopo):
    return to_netkat_realnoid_paths_for_hosts(graph, [graph.hosts[0], graph.hosts[3]], withTopo=withTopo)

#########

def to_netkat_regular(graph, withTopo=True):
    # succinct program that exploits regularity
    policy = []

    core_flt = []
    for sw in graph.core_switches:
        flt = "filter switch = %d" % (graph.node[sw]['id'])
        core_flt.append(flt)

    core_policy = []
    for host in graph.hosts:
        port = ((int(host[1:]) - 1) / (2*graph.p)) + 1
        s = string.join(("filter ethDst = %s" % (graph.node[host]['mac']), "port := %d" % (port)), "; ")
        core_policy.append(s)

    policy.append("((%s); (%s))" % (string.join(core_flt, " | "), string.join(core_policy, " | ")))

    agg_flt = []
    for sw in graph.agg_switches:
        flt = "filter switch = %d" % (graph.node[sw]['id'])
        agg_flt.append(flt)

    agg_policy = []
    # every agg sw has the same port-based filters; use the first
    sw = graph.agg_switches[0]
    for k, v in graph.node[sw]['routes'].iteritems():
        if isinstance(k, int):
            s = string.join(("filter port = %d" % (k), "port := %d" % (v)), "; ")
            agg_policy.append(s)

    policy.append("((%s); (%s))" % (string.join(agg_flt, " | "), string.join(agg_policy, " | ")))

    edge_flt = []
    for sw in graph.edge_switches:
        flt = "filter switch = %d" % (graph.node[sw]['id'])
        edge_flt.append(flt)

    edge_policy = []
    # every agg sw has the same port-based filters; use the first
    sw = graph.edge_switches[0]
    for k, v in graph.node[sw]['routes'].iteritems():
        if isinstance(k, int):
            s = string.join(("filter port = %d" % (k), "port := %d" % (v)), "; ")
            edge_policy.append(s)

    policy.append("((%s); (%s))" % (string.join(edge_flt, " | "), string.join(edge_policy, " | ")))

    agg_policy = []
    for sw in graph.agg_switches:
        flt = "filter switch = %d" % (graph.node[sw]['id'])
        for k, v in graph.node[sw]['routes'].iteritems():
            if k in graph.hosts:
                s = string.join((flt, "filter ethDst = %s" % (graph.node[k]['mac']), "port := %d" % (v)), "; ")
                agg_policy.append("(%s)" % (s))

    policy.extend(agg_policy)

    # every agg sw has the same port-based filters; use the first
    edge_policy = []
    for sw in graph.edge_switches:
        flt = "filter switch = %d" % (graph.node[sw]['id'])
        for k, v in graph.node[sw]['routes'].iteritems():
            if k in graph.hosts:
                s = string.join((flt, "filter ethDst = %s" % (graph.node[k]['mac']), "port := %d" % (v)), "; ")
                edge_policy.append("(%s)" % (s))

    if withTopo:
        topo = []
        for src, dst, ed in graph.edges_iter(data=True):
            if src in graph.hosts or dst in graph.hosts:
                continue
            topoterm = "%s@%d => %s@%d" % (graph.node[src]['id'], ed['sport'], graph.node[dst]['id'], ed['dport'])
            topo.append(topoterm)

        edge_topo = []
        for host in graph.hosts:
            dst = graph.neighbors(host)[0]
            ed = graph.get_edge_data(host, dst)
            topoterm = "%s@%d => 0@%d" % (graph.node[dst]['id'], ed['dport'], graph.node[host]['id'])
            edge_topo.append(topoterm)

    if withTopo:
        return "((\n%s\n);\n(\n%s\n))*;\n((\n%s\n);\n(\n%s\n))" % \
            (string.join(policy, " |\n"), string.join(topo, " |\n"),
             string.join(edge_policy, " |\n"), string.join(edge_topo, " |\n"))
    else:
        policy.extend(edge_policy)
        return "%s\n" % (string.join(policy, " |\n"))


def to_netkat(graph, kattype, katfile, failover, local):
    for node in graph.switches:
        graph.node[node]['routes'] = {}
        l = (graph.node[node]['id'] - 1) / (2*graph.p**graph.L)
        graph.node[node]['level'] = l
    for node in graph.hosts:
        rec_routing_downwards(graph, node, node, 0)
    n = len(graph.switches) - graph.p**graph.L
    noncore_switches = graph.switches[0:n]
    for node in noncore_switches:
        routing_upwards(graph, node)
    #print nx.to_agraph(graph)
    withTopo = not local
    if failover:
        if kattype == 'tables':
            policy = to_netkat_set_of_tables_failover(graph, withTopo=withTopo)
        elif kattype == 'testtables':
            policy = to_netkat_test_set_of_tables_failover(graph, withTopo=withTopo)
        else:
            raise "Unsupported"
    else:
        if kattype == 'tables':
            policy = to_netkat_set_of_tables(graph, withTopo=withTopo)
        elif kattype == 'testtables':
            policy = to_netkat_test_set_of_tables(graph, withTopo=withTopo)
        elif kattype == 'paths':
            policy = to_netkat_set_of_paths(graph, withTopo=withTopo)
        elif kattype == 'testpaths':
            policy = to_netkat_test_set_of_paths(graph, withTopo=withTopo)
        elif kattype == 'testpaths2':
            policy = to_netkat_test_set_of_paths2(graph, withTopo=withTopo)
        elif kattype == 'regular':
            policy = to_netkat_regular(graph, withTopo=withTopo)
        elif kattype == 'realpaths':
            policy = to_netkat_real_paths(graph, withTopo=withTopo)
        elif kattype == 'testrealpaths':
            policy = to_netkat_test_real_paths(graph, withTopo=withTopo)
        elif kattype == 'testrealpaths2':
            policy = to_netkat_test_real_paths2(graph, withTopo=withTopo)
        elif kattype == 'realnoidpaths':
            policy = to_netkat_realnoid_paths(graph, withTopo=withTopo)
        elif kattype == 'testnoidrealpaths':
            policy = to_netkat_test_realnoid_paths(graph, withTopo=withTopo)
        elif kattype == 'testnoidrealpaths2':
            policy = to_netkat_test_realnoid_paths2(graph, withTopo=withTopo)
        else:
            raise "Unsupported"

    if katfile:
        with open(katfile, 'w') as f:
            f.write(policy)
    else:
        print policy

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("fanout", type=int,
                        help="number of children each node should have")
    parser.add_argument("depth", type=int,
                        help="depth of the fattree")
    parser.add_argument("-o", "--out", dest='output', action='store',
                        default=None,
                        help='file to write to')
    parser.add_argument("-k", "--kat", dest='katfile', action='store',
                        default=None,
                        help='file to write to')
    parser.add_argument("-f", "--ft", dest='failover', action='store',
                        default='nofail',
						type = str,
                        choices=['nofail', 'fail'],
                        help='output failover')
    parser.add_argument("-l", "--local", dest='local', action='store',
                        default='full',
						type = str,
                        choices=['full', 'local'],
                        help='output local')
    parser.add_argument("-t", "--type",
                        help='KAT policy type',
                        dest='kattype',
                        action='store',
                        choices=['tables', 'paths', 'regular', 'realpaths', 'realnoidpaths', 'testpaths', 'testpaths2', 'testrealpaths', 'testrealpaths2', 'testnoidrealpaths', 'testnoidrealpaths2', 'testtables'],
                        default='tables',
                        type=str)

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    graph = generate(args.fanout, args.depth)

    if args.output:
        nx.write_dot(graph,args.output)
    else:
        print nx.to_agraph(graph)
    to_netkat(graph, args.kattype, args.katfile, args.failover == 'fail', args.local == 'local')
