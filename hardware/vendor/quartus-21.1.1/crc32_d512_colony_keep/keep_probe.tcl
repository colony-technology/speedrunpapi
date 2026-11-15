package require ::quartus::atoms
package require ::quartus::names
package require ::quartus::project
foreach c {read_atom_netlist get_atom_nodes get_atom_node_info get_names} {puts "$c HELP"; puts "[catch {$c -help} msg] $msg"}
