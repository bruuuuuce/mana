#!/usr/bin/env perl
use strict;
use warnings;
use Fcntl qw(F_GETFL F_SETFL O_NONBLOCK);
use IO::Select;
use POSIX qw(:sys_wait_h setsid WIFEXITED WEXITSTATUS WIFSIGNALED WTERMSIG);
use Time::HiRes qw(time sleep);

my ($timeout, $cap, $stdout_path, $stderr_path, $status_path);
while (@ARGV) {
    my $arg = shift @ARGV;
    last if $arg eq '--';
    if ($arg eq '--timeout') { $timeout = shift @ARGV; next; }
    if ($arg eq '--output-cap') { $cap = shift @ARGV; next; }
    if ($arg eq '--stdout') { $stdout_path = shift @ARGV; next; }
    if ($arg eq '--stderr') { $stderr_path = shift @ARGV; next; }
    if ($arg eq '--status') { $status_path = shift @ARGV; next; }
    die "unknown supervisor option: $arg\n";
}
die "invalid supervisor arguments\n" unless defined($timeout) && $timeout =~ /^\d+$/ && $timeout > 0
    && defined($cap) && $cap =~ /^\d+$/ && $cap >= 0
    && defined($stdout_path) && defined($stderr_path) && defined($status_path) && @ARGV;

open my $saved_out, '>:raw', $stdout_path or die "open stdout artifact: $!\n";
open my $saved_err, '>:raw', $stderr_path or die "open stderr artifact: $!\n";
pipe(my $out_read, my $out_write) or die "stdout pipe: $!\n";
pipe(my $err_read, my $err_write) or die "stderr pipe: $!\n";

my $started = time;
my ($pid, $parent_active) = (undef, 0);
$pid = fork();
die "fork: $!\n" unless defined $pid;
if ($pid == 0) {
    eval { setsid() } or do { print {$err_write} "verification supervisor setsid failed: $!\n"; POSIX::_exit(125); };
    close $out_read; close $err_read;
    open STDOUT, '>&', $out_write or POSIX::_exit(125);
    open STDERR, '>&', $err_write or POSIX::_exit(125);
    close $out_write; close $err_write;
    no warnings 'exec';
    exec { $ARGV[0] } @ARGV;
    print STDERR "verification exec failed: $!\n";
    POSIX::_exit(125);
}
$parent_active = 1;
# Any supervisor exception or external interruption must not strand the
# verification process group. The child inherits parent_active=0.
END {
    if ($parent_active && $pid) {
        kill 'TERM', -$pid;
        sleep 0.1;
        kill 'KILL', -$pid;
        waitpid($pid, 0);
    }
}
close $out_write; close $err_write;
for my $handle ($out_read, $err_read) {
    my $flags = fcntl($handle, F_GETFL, 0);
    fcntl($handle, F_SETFL, $flags | O_NONBLOCK) or die "nonblocking pipe: $!\n";
}

my $selector = IO::Select->new($out_read, $err_read);
my %kind = (fileno($out_read) => 'stdout', fileno($err_read) => 'stderr');
my %bytes = (stdout => 0, stderr => 0);
my %kept = (stdout => 0, stderr => 0);
my %sink = (stdout => $saved_out, stderr => $saved_err);
my ($wait_status, $leader_done, $timed_out, $descendants_terminated) = (0, 0, 0, 0);

sub terminate_group {
    my ($signal) = @_;
    kill $signal, -$pid if $pid;
}
$SIG{INT} = sub { exit 130; };
$SIG{TERM} = sub { exit 143; };

sub drain_ready {
    my ($wait) = @_;
    for my $handle ($selector->can_read($wait)) {
        my $buffer = '';
        my $read = sysread($handle, $buffer, 65536);
        if (!defined $read) { next if $!{EAGAIN} || $!{EINTR}; die "read child output: $!\n"; }
        if ($read == 0) { $selector->remove($handle); close $handle; next; }
        my $stream = $kind{fileno($handle)};
        $bytes{$stream} += $read;
        my $remaining = $cap - $kept{$stream};
        if ($remaining > 0) {
            my $piece = substr($buffer, 0, $remaining);
            print { $sink{$stream} } $piece or die "write bounded output: $!\n";
            $kept{$stream} += length($piece);
        }
    }
}

my $deadline = $started + $timeout;
while (!$leader_done) {
    drain_ready(0.05);
    my $waited = waitpid($pid, WNOHANG);
    if ($waited == $pid) { $wait_status = $?; $leader_done = 1; last; }
    if (time >= $deadline) {
        $timed_out = 1;
        terminate_group('TERM');
        my $grace = time + 0.5;
        while (time < $grace) {
            drain_ready(0.05);
            $waited = waitpid($pid, WNOHANG);
            if ($waited == $pid) { $wait_status = $?; $leader_done = 1; last; }
        }
        if (!$leader_done) { terminate_group('KILL'); waitpid($pid, 0); $wait_status = $?; $leader_done = 1; }
    }
}

# Descendants may inherit the pipes after the leader exits. They are not part
# of a bounded verification result, so terminate the child's process group.
if ($selector->count) {
    my $drain_deadline = time + 0.2;
    while ($selector->count && time < $drain_deadline) { drain_ready(0.02); }
    if ($selector->count) {
        $descendants_terminated = 1;
        terminate_group('TERM'); sleep 0.1; terminate_group('KILL');
        my $close_deadline = time + 0.2;
        while ($selector->count && time < $close_deadline) { drain_ready(0.02); }
    }
}
# A descendant can close both inherited streams and still remain in the
# command process group. Detect and terminate that case as well.
if (kill 0, -$pid) {
    $descendants_terminated = 1;
    terminate_group('TERM'); sleep 0.1; terminate_group('KILL');
}
for my $handle ($selector->handles) { $selector->remove($handle); close $handle; }
close $saved_out; close $saved_err;

my ($exit_code, $signal) = (0, 0);
if (WIFEXITED($wait_status)) { $exit_code = WEXITSTATUS($wait_status); }
elsif (WIFSIGNALED($wait_status)) { $signal = WTERMSIG($wait_status); $exit_code = 128 + $signal; }
else { $exit_code = 125; }
my $duration_ms = int((time - $started) * 1000 + 0.5);
open my $status, '>', $status_path or die "open supervisor status: $!\n";
print {$status} join("\t", $exit_code, $signal, $timed_out, $descendants_terminated,
    $bytes{stdout}, $bytes{stderr}, $duration_ms), "\n";
close $status or die "close supervisor status: $!\n";
$parent_active = 0;
exit 0;
