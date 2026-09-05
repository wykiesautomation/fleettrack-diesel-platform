# OPC UA Part 2: Node Browser and Read Test

- Queues browse/read work for the assigned local Edge Gateway.
- Adds server-side tenant, gateway and request-ID validation.
- Supports root node, depth, node count, search and datatype filters.
- Displays Node ID, display/browse name, datatype, value, quality and source/server timestamps.
- Hard-limits browse results to 1,000 nodes.
- Includes a read-only local Edge executor with no write or method-call capability.
