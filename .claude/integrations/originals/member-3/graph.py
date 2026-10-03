import networkx as nx
from db import get_all

def build_graph():
    G = nx.DiGraph()
    for e in get_all("entities"):
        G.add_node(e["entity_id"], name=e["name"], type=e["type"])
    for r in get_all("relationships"):
        G.add_edge(r["subject"], r["object"], predicate=r["predicate"],
                    source=r["source_document"], page=r["source_page"])
    return G

def get_entity_network(entity_id: str, depth: int = 2):
    G = build_graph()
    if entity_id not in G:
        return {"error": "entity not found"}
    sub = nx.ego_graph(G.to_undirected(), entity_id, radius=depth)
    nodes = [{"entity_id": n, "name": G.nodes[n].get("name"), "type": G.nodes[n].get("type")}
             for n in sub.nodes if G.nodes[n].get("name")]
    valid_ids = {n["entity_id"] for n in nodes}
    edges = [{"from": u, "to": v, "predicate": d.get("predicate"),
              "source": d.get("source"), "page": d.get("page")}
             for u, v, d in G.edges(data=True)
             if u in valid_ids and v in valid_ids]
    return {"nodes": nodes, "edges": edges}