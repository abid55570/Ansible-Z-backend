"""Infrastructure-as-data: an IR (graph of resource blocks) that compiles to Ansible.

A template is a fixed design; a user's custom design is an open one. Both are the same
graph, compiled by the same engine (validate -> topo-sort -> render+wire -> assemble).
"""
