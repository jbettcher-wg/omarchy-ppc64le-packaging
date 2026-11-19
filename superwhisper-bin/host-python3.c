/* superwhisper-bin, ppc64le: a native python3 for Superwhisper's helper scripts.
 *
 * Superwhisper's aarch64 build runs under POWERarm and starts its helper
 * scripts (media pause, the Omarchy indicator, deep links) as "python3" from
 * PATH. Under POWERarm that name resolves through the guest root first, so a
 * guest that holds its own python3 -- any guest where something pulled Python
 * in -- runs them on an aarch64 interpreter, which then finds the host's
 * ppc64le gi bindings and cannot load them ("cannot import name '_gi'").
 *
 * POWERarm runs a native executable natively, and a native process sees the
 * host's filesystem. So this native binary, first on Superwhisper's PATH,
 * hands the script to the host's python3, which has the gi, cairo and
 * layer-shell bindings the package depends on.
 *
 * A symlink or a #! script would not do: POWERarm resolves both inside the
 * guest root, back to the guest's interpreter.
 */
#include <stdio.h>
#include <unistd.h>

int main(int argc, char **argv) {
  (void)argc;
  argv[0] = "/usr/bin/python3";
  execv("/usr/bin/python3", argv);
  perror("superwhisper: /usr/bin/python3");
  return 127;
}
