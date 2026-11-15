project_open colony -revision colony
create_timing_netlist
read_sdc
update_timing_netlist
set regs [all_registers]
report_timing -setup -from $regs -to $regs -npaths 10 -detail full_path -file register_paths.rpt
report_clock_fmax_summary -file clock_fmax.rpt
report_clocks -file clock_setup.rpt
delete_timing_netlist
project_close
