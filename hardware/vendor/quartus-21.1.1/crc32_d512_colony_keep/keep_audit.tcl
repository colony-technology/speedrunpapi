package require ::quartus::project
package require ::quartus::names
project_open colony -revision colony
foreach phase {pre_synthesis post_synthesis post_fitter} {
 set coll [get_names -filter {*|n*} -observable_type $phase]
 puts "PHASE $phase collection_size [get_collection_size $coll]"
}
project_close
