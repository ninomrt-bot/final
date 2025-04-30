# hmi.py  ────────────────────────────────────────────────────────────
"""
IHM "Poste de Pilotage LGN-04"
 ─ Consomme l’API REST :  http://10.10.0.23:5000/api
 ─ Écrit l’OF dans l’automate via OPC-UA : opc.tcp://172.30.30.11:4840
"""

import datetime, os, tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from pathlib import Path
from PIL import Image, ImageTk

import rest_client            # <- wrapper REST fourni
#import opcua_client           # <- wrapper OPC-UA fourni

# ------------------------------------------------------------------ #
# 1)   CONSTANTES PROJET                                             #
# ------------------------------------------------------------------ #
ASSETS_DIR      = "/home/groupec/Documents/NEE/Assets"   # logo + drapeaux
BADGE_OPERATEUR = '&("(&c&-'
                        

TRANSLATIONS = {
    "fr": {
        "title":          "Poste de Pilotage LGN-04",
        "dashboard":      "Accueil",
        "of_selection":   "Ordres de Fabrication",
        "status":         "État des îlots",
        "logs":           "Logs",
        "traceability":   "Traçabilité",
        "unauthorized":   "Veuillez scanner votre badge RFID.",
        "export_logs":    "Exporter les logs",
        "send_of":        "Envoyer l’OF sélectionné",
        "badge_wait":     "Veuillez scanner votre badge RFID…",
        "no_of_selected": "Sélectionnez un OF dans la liste.",
        "send_success":   "OF {numero} envoyé avec succès.",
        "send_error":     "Impossible d’envoyer l’OF.",
        "clear_logs":     "🧹  Vider les logs",
        "filter_label":   "🔎  Filtrer :",
        "details":        "Détails"
    },
    "en": {
        "title":          "Production Dashboard LGN-04",
        "dashboard":      "Dashboard",
        "of_selection":   "Manufacturing Orders",
        "status":         "Station Status",
        "logs":           "Logs",
        "traceability":   "Traceability",
        "unauthorized":   "Scan your RFID badge first.",
        "export_logs":    "Export logs",
        "send_of":        "Send selected MO",
        "badge_wait":     "Please scan your RFID badge…",
        "no_of_selected": "Select an MO in the list.",
        "send_success":   "MO {numero} successfully sent.",
        "send_error":     "Unable to send the MO.",
        "clear_logs":     "🧹  Clear logs",
        "filter_label":   "🔎  Filter :",
        "details":        "Details"
    },
}

# ------------------------------------------------------------------ #
# 2)   APPLICATION Tk                                                #
# ------------------------------------------------------------------ #
class PilotageApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.geometry("1280x720")
        self.title("Pilotage LGN-04")
        self.configure(bg="#10142c")

        # état
        self.lang          = "fr"
        self.role          = "non_identifié"
        self.logs: list[tuple[str,str]] = []
        self.search_var    = tk.StringVar()
        self.traceability_data: list[tuple[str,str,str]] = []

        # ------------------------------------------------------------------
        #   BARRE HAUTE
        # ------------------------------------------------------------------
        topbar = tk.Frame(self, bg="#1b1f3b", height=60)
        topbar.pack(side="top", fill="x")

        self.title_label = tk.Label(
            topbar, text=self.tr("title"),
            font=("Segoe UI", 18, "bold"), fg="white", bg="#1b1f3b"
        )
        self.title_label.pack(side="left", padx=20)

        self.rest_status = tk.Label(
            topbar, text="REST : ???", font=("Segoe UI", 12),
            fg="white", bg="#1b1f3b"
        )
        self.rest_status.pack(side="right", padx=15)

        self.role_label = tk.Label(
            topbar, text=f"Rôle : {self.role}", font=("Segoe UI", 12),
            fg="white", bg="#1b1f3b"
        )
        self.role_label.pack(side="right")

        # boutons langue
        flag_frame = tk.Frame(topbar, bg="#1b1f3b")
        flag_frame.pack(side="right", padx=10)
        self._add_flag(flag_frame, "fr", "autocollant-drapeau-france-rond.jpg")
        self._add_flag(flag_frame, "en", "sticker-drapeau-anglais-rond.jpg")

        # ------------------------------------------------------------------
        #   SIDEBAR & CONTENU
        # ------------------------------------------------------------------
        sidebar = tk.Frame(self, bg="#16193c", width=200)
        sidebar.pack(side="left", fill="y")

        self.content = tk.Frame(self, bg="#202540")
        self.content.pack(side="right", expand=True, fill="both")

        # boutons navigation
        self.nav_btns: list[tk.Button] = []
        for key, cb in (
            ("dashboard",      self.show_dashboard),
            ("of_selection",   lambda: self.need_auth(self.show_of)),
            ("status",         lambda: self.need_auth(self.show_status)),
            ("logs",           lambda: self.need_auth(self.show_logs)),
            ("traceability",   lambda: self.need_auth(self.show_trace))
        ):
            b = tk.Button(sidebar, text=self.tr(key),
                          font=("Segoe UI", 13), bg="#16193c", fg="white",
                          activebackground="#3047ff", relief="flat",
                          command=cb)
            b.pack(fill="x", padx=10, pady=6)
            self.nav_btns.append(b)

        # frames (pages)
        self.frames = {name: tk.Frame(self.content, bg="#202540")
                       for name in ("dash","of","status","logs","trace")}
        for f in self.frames.values():
            f.place(relwidth=1, relheight=1, x=0, y=0)

        # widgets variables
        self.tree_of   = None
        self.tree_logs = None

        # zone scan badge cachée
        self._hidden = tk.Entry(self)
        self._hidden.place(x=-100,y=-100)
        self._hidden.bind("<Return>", self._on_badge)
        self._hidden.focus()

        # logo centre
        self.logo_img = ImageTk.PhotoImage(
            Image.open(Path(ASSETS_DIR)/"logoENN.PNG").resize((200,200))
        )

        self.load_traceability()
        self.show_dashboard()

    # ------------------------------------------------------------------ #
    #   OUTILS
    # ------------------------------------------------------------------ #
    def tr(self, k): return TRANSLATIONS[self.lang].get(k,k)

    def _add_flag(self, frame, lang, file):
        img = ImageTk.PhotoImage(Image.open(Path(ASSETS_DIR)/file).resize((32,32)))
        tk.Button(frame, image=img, bd=0, bg="#1b1f3b",
                  command=lambda l=lang: self.set_lang(l)).pack(side="left", padx=3)
        setattr(self, f"flag_{lang}", img)          # garder réf.

    def set_lang(self, lang):
        self.lang = lang
        self.title_label.config(text=self.tr("title"))
        for b,key in zip(self.nav_btns,
                         ("dashboard","of_selection","status","logs","traceability")):
            b.config(text=self.tr(key))
        self.show_dashboard()

    # ------------------------------------------------------------------ #
    #   AUTH
    # ------------------------------------------------------------------ #
    def _on_badge(self, _):
        code = self._hidden.get().strip(); self._hidden.delete(0,'end')
        if code == BADGE_OPERATEUR:
            self.role = "opérateur"
            self.role_label.config(text=f"Rôle : {self.role}")
            self.log("Badge opérateur OK")
        else:
            self.role = "non_identifié"
            self.role_label.config(text=f"Rôle : {self.role}")
            messagebox.showerror("Badge", "Badge invalide")
            self.log("Badge refusé")

    def need_auth(self, fn):
        if self.role == "non_identifié":
            messagebox.showwarning("Accès", self.tr("unauthorized"))
        else:
            fn()

    # ------------------------------------------------------------------ #
    #   REST status
    # ------------------------------------------------------------------ #
    def update_rest_status(self):
        ok = rest_client.can_connect_to_rest()
        self.rest_status.config(
            text=f"REST : {'OK' if ok else 'OFF'}",
            fg="lightgreen" if ok else "red"
        )

    # ------------------------------------------------------------------ #
    #   PAGES
    # ------------------------------------------------------------------ #
    def show_frame(self, tag):
        for f in self.frames.values():
            f.lower()
        self.frames[tag].tkraise()

    # ----- dashboard
    def show_dashboard(self):
        self.update_rest_status()
        f = self.frames["dash"];   self._clear(f);  self.show_frame("dash")
        tk.Label(f, image=self.logo_img, bg="#202540").pack(pady=20)
        tk.Label(f, text=self.tr("title"), fg="white", bg="#202540",
                 font=("Segoe UI",20)).pack(pady=10)
        tk.Label(f, text=datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
                 fg="white", bg="#202540", font=("Segoe UI",14)).pack()
        if self.role=="non_identifié":
            tk.Label(f, text=self.tr("badge_wait"),
                     fg="lightgray", bg="#202540").pack(pady=30)

    # ----- liste OF
    def show_of(self):
        self.update_rest_status()
        f=self.frames["of"]; self._clear(f); self.show_frame("of")
        tk.Label(f, text=self.tr("of_selection"),
                 fg="white", bg="#202540", font=("Segoe UI",18,"bold")
                 ).pack(pady=8)

        self.tree_of = ttk.Treeview(f, columns=("Num","Code","Qté"),
                                    show="headings", height=15)
        for col,w in (("Num",160),("Code",420),("Qté",100)):
            self.tree_of.heading(col, text=col); self.tree_of.column(col,width=w)
        self.tree_of.pack(padx=10,pady=12)
        self.tree_of.bind("<Double-1>", self.details_of)

        # REST
        try:
            for of in rest_client.get_of_list_cached():
                self.tree_of.insert("", "end",
                                    values=(of["numero"],of["code"],of["quantite"]))
            self.log("Liste OF chargée")
        except Exception as e:
            self.log(f"REST KO : {e}")
            messagebox.showerror("REST", "Impossible de récupérer la liste OF.")

        tk.Button(f, text=self.tr("send_of"), bg="green", fg="white",
                  command=self.send_selected).pack(pady=6)

    def details_of(self, _):
        sel=self.tree_of.selection();  self.tree_of.focus()
        if not sel: return
        num = self.tree_of.item(sel[0],"values")[0]
        comps= rest_client.get_of_components(num)
        p=tk.Toplevel(self); p.title(f"{self.tr('details')} – {num}")
        p.configure(bg="#202540"); p.geometry("420x300")
        tk.Label(p,text=f"OF {num}",bg="#202540", fg="white",
                 font=("Arial",14,"bold")).pack(pady=8)
        for c in comps:
            tk.Label(p,text=c,bg="#202540",fg="white", anchor="w").pack(fill="x",padx=20)

    def send_selected(self):
            sel = self.tree_of.selection()
            if not sel:
                return messagebox.showwarning("!", self.tr("no_of_selected"))
            values = self.tree_of.item(sel[0], "values")
            of_num = values[0]
            code   = values[1]
            try:
                qty = float(values[2])
            except ValueError:
                messagebox.showerror("Erreur", "Quantité invalide")
                return

            ilot = simpledialog.askstring("Îlot", "Entrer LGN01 / LGN02 / LGN03 :")
            if ilot not in ("LGN01","LGN02","LGN03"):
                return

            # date actuelle si non renseignée
            date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # appel rest_client.start avec tous les paramètres
            if rest_client.start(ilot, of_num, code, qty, date_str):
                self.log(f"{of_num} → {ilot} OK"); messagebox.showinfo("OK", self.tr("send_success").format(numero=of_num))
            else:
                self.log(f"{of_num} → {ilot} KO"); messagebox.showerror("KO", self.tr("send_error"))


    # ----- status (simple démo)
    def show_status(self):
        self.update_rest_status()
        f = self.frames["status"]; self._clear(f); self.show_frame("status")
        tk.Label(f, text=self.tr("status"), fg="white", bg="#202540",
                font=("Segoe UI",18,"bold")).pack(pady=8)

        states = rest_client.status()
        for s in states:
            tk.Label(f, text=f"{s['ilot']} : {s['etat']}",
                    fg="lightgreen" if s['etat']=="ON" else "yellow",
                    bg="#202540", font=("Segoe UI",14)).pack(pady=4)



    # ----- logs
    def show_logs(self):
        f=self.frames["logs"]; self._clear(f); self.show_frame("logs")
        tk.Label(f,text=self.tr("logs"),fg="white",bg="#202540",
                 font=("Segoe UI",18)).pack(pady=8)

        search = tk.Entry(f,textvariable=self.search_var)
        search.pack(); search.bind("<KeyRelease>", self.refresh_logs)

        tk.Button(f,text=self.tr("export_logs"), command=self.export_logs).pack(pady=3)
        tk.Button(f,text=self.tr("clear_logs"),  command=self.clear_logs ).pack()

        self.tree_logs = ttk.Treeview(f, columns=("t","m"),show="headings",height=18)
        self.tree_logs.heading("t",text="Heure"); self.tree_logs.column("t",width=165)
        self.tree_logs.heading("m",text="Message"); self.tree_logs.column("m",width=820)
        self.tree_logs.pack(padx=10,pady=10)
        self.refresh_logs()

    # ----- trace (simulation)
    def load_traceability(self):
        self.traceability_data = [
            ("WH/MO/00012","En cours","2025-02-27 14:22"),
            ("WH/MO/00011","OK","2025-02-27 11:05")
        ]

    def show_trace(self):
        f=self.frames["trace"]; self._clear(f); self.show_frame("trace")
        tk.Label(f,text=self.tr("traceability"),fg="white",bg="#202540",
                 font=("Segoe UI",18,"bold")).pack(pady=10)

        tree=ttk.Treeview(f, columns=("OF","Etat","Horodatage"),show="headings", height=16)
        for col,w in (("OF",160),("Etat",220),("Horodatage",250)):
            tree.heading(col,text=col); tree.column(col,width=w)
        tree.pack(padx=12,pady=12)
        for row in self.traceability_data: tree.insert("", "end", values=row)

    # ------------------------------------------------------------------ #
    #   LOGS utils
    # ------------------------------------------------------------------ #
    def log(self,msg:str):
        ts=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.logs.append((ts,msg)); self.refresh_logs(); print(ts,msg)

    def refresh_logs(self,*_):
        if not self.tree_logs: return
        filt=self.search_var.get().lower()
        self.tree_logs.delete(*self.tree_logs.get_children())
        for t,m in self.logs:
            if filt in t.lower() or filt in m.lower():
                self.tree_logs.insert("", "end", values=(t,m))

    def clear_logs(self):
        if messagebox.askyesno("?", self.tr("clear_logs")):
            self.logs.clear(); self.refresh_logs()

    def export_logs(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                                            filetypes=[("CSV","*.csv")])
        if not path: return
        with open(path,"w",encoding="utf-8") as f:
            f.write("Heure,Message\n")
            for t,m in self.logs: f.write(f"{t},{m}\n")
        messagebox.showinfo("Export", f"{len(self.logs)} logs → {path}")

    # ------------------------------------------------------------------ #
    #   DIVERS
    # ------------------------------------------------------------------ #
    def _clear(self, frame): [w.destroy() for w in frame.winfo_children()]

# ---------------------------------------------------------------------- #
if __name__ == "__main__":
    app = PilotageApp()
    app.mainloop()
