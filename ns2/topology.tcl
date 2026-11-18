set ns [new Simulator]
file mkdir artifacts/ns2
set trace [open "artifacts/ns2/$scenario.tr" w]
$ns trace-all $trace

for {set i 0} {$i < 4} {incr i} {
    set n($i) [$ns node]
}
$ns duplex-link $n(0) $n(1) 10Mb 5ms DropTail
$ns duplex-link $n(2) $n(3) 10Mb 5ms DropTail
if {$scenario eq "impaired"} {
    $ns duplex-link $n(1) $n(2) 0.5Mb 80ms DropTail
    $ns queue-limit $n(1) $n(2) 3
} else {
    $ns duplex-link $n(1) $n(2) 2Mb 10ms DropTail
    $ns queue-limit $n(1) $n(2) 50
}

set tcp [new Agent/TCP/Reno]
$tcp set packetSize_ 1000
$tcp set fid_ 1
$ns attach-agent $n(0) $tcp
set sink [new Agent/TCPSink]
$ns attach-agent $n(3) $sink
$ns connect $tcp $sink
set ftp [new Application/FTP]
$ftp attach-agent $tcp

proc finish {} {
    global ns trace
    $ns flush-trace
    close $trace
    exit 0
}
$ns at 0.5 "$ftp start"
$ns at 8.5 "$ftp stop"
$ns at 10.0 "finish"
$ns run
