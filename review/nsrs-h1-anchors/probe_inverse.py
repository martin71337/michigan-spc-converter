"""H1 item 4 -- does beta NCAT accept SPC (N/E/zone) as INPUT?

The initial app page renders only the lat-lon input panel; the SPC panel is
built by a PrimeFaces valueChange AJAX on tv1:f1:proj1. So the question is
answered by firing that AJAX and reading what field names come back.

Run:  py -3 probe_inverse.py
"""

from __future__ import annotations

import os
import re

import h1_lib as H


def main():
    n = H.Ncat()
    n.open_app()
    print("app page opened; action=%s" % H.scrub_url(n.action))

    f = n.base_fields()
    f["tv1:f1:proj1"] = "spc"
    f.update({
        "javax.faces.partial.ajax": "true",
        "javax.faces.source": "tv1:f1:proj1",
        "javax.faces.partial.execute": "tv1:f1:proj1",
        "javax.faces.partial.render": "tv1:f1:p1 tv1:f1:resultP",
        "javax.faces.behavior.event": "valueChange",
        "javax.faces.partial.event": "change",
    })
    rec, body = n.post(f, "inv_probe_proj1_spc.xml",
                       note="valueChange proj1=spc -- discover SPC input panel")
    print("status=%s bytes=%s sha256=%s" %
          (rec["status"], rec["bytes"], rec["sha256"]))
    if not body:
        print("NO BODY: %s" % rec["error"])
        return

    names = sorted(set(re.findall(r'name="(tv1:f1:[^"]+)"', body)))
    print("\nfield names in the partial response (%d):" % len(names))
    for x in names:
        print("   ", x)

    print("\nlabels:")
    for m in re.finditer(r"<label[^>]*>([^<]{1,60})</label>", body):
        t = m.group(1).strip()
        if t:
            print("   ", t)

    print("\nzone/units selects:")
    for m in re.finditer(r'<select[^>]*name="(tv1:f1:[^"]+)"[^>]*>(.*?)</select>',
                         body, re.S):
        opts = re.findall(r'<option[^>]*value="([^"]*)"', m.group(2))
        print("   %s : %d options; first 6 %r" % (m.group(1), len(opts), opts[:6]))

    n.write_manifest("inv_probe_manifest.json")
    print("\nsaved %s" % os.path.join(H.RAW, "inv_probe_proj1_spc.xml"))


if __name__ == "__main__":
    main()
