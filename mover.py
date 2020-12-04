#!/usr/bin/env python3
import smtplib
import shutil
import os
import glob
import logging
import logging.handlers
import sys
from email.message import EmailMessage
from datetime import datetime
from configparser import ConfigParser
from subprocess import call, Popen, PIPE, STDOUT


__author__ = "Andrea Magista'"
__version__ = "1.0.1"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_DIR = os.path.join(BASE_DIR, "backup/")
CONF_PATH = os.path.join(BASE_DIR, "backup/mover.cfg")
LOG_DIR = os.path.join(BASE_DIR, "backup/log/")


def send_mail(msg_from="Backup Storico",
              sender="backup@distillerieberta.it",
              receiver="administrator@distillerieberta.it",
              smtp_name="10.0.0.35",
              smtp_port=25,
              attach_name=None,
              subject="",
              content=""
              ):
    conf = Configurator(CONF_PATH)
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = "{} <{}>".format(msg_from, sender)
    msg["To"] = receiver
    msg.set_content(content)

    if attach_name is not None:
        try:
            with open(attach_name) as attachment:
                attachment_data = attachment.read()

            msg.add_attachment(attachment_data, filename=conf.get("log", "name"))
        except FileNotFoundError:
            print("Impossibile trovare l' allegato specificato. Invio email bloccato")
            return sys.exit()
    with smtplib.SMTP(smtp_name, smtp_port) as smtp:
        smtp.send_message(msg)
        print("Email Inviata con successo all' indirizzo {}!".format(receiver))


def disk_usage_gb(fullpath):
    total, used, free = shutil.disk_usage(fullpath)
    total_in_gb = float(round(total / 1024 / 1024 / 1024, 2))
    used_in_gb = float(round(used / 1024 / 1024 / 1024, 2))
    free_in_gb = float(round(free / 1024 / 1024 / 1024, 2))
    return total_in_gb, used_in_gb, free_in_gb


def logger():
    """ crea oggetto logger """
    configuration = Configurator(CONF_PATH)
    log_name = configuration.get("log", "name")
    log_path = os.path.join(LOG_DIR, "{}".format(log_name))
    if not os.path.exists(os.path.dirname(log_path)):
        os.makedirs(os.path.dirname(log_path))
    log = logging.getLogger()
    if configuration.get("log", "level") == "debug":
        log.setLevel(logging.DEBUG)
        formatter = logging.Formatter("[%(name)s][%(levelname)s]      %(funcName)20s =>     %(message)s")
    else:
        log.setLevel(logging.INFO)
        formatter = logging.Formatter("[%(levelname)s] %(asctime)s : %(message)s")

    # file_handler
    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(formatter)

    # rotate_handler
    log_count = int(configuration.get("log", "count"))
    rotate_handler = logging.handlers.RotatingFileHandler(log_path, mode="w", backupCount=log_count)
    rotate_handler.setFormatter(formatter)
    log.addHandler(rotate_handler)

    # Effettuo rotazione backup
    should_roll_over = os.path.isfile(log_path)
    if should_roll_over:
        rotate_handler.doRollover()

    # stream_handler
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    # Aggiungo handlers
    log.addHandler(stream_handler)
    log.addHandler(file_handler)

    return log


class Configurator:
    def __init__(self, conf_file):
        self.conf_file = conf_file
        self.configuration = ConfigParser()
        self.configuration.read(self.conf_file)

    def get_as_list(self, section, key):
        """ Acquisisce i dati dal file di configurazione come una lista"""
        raw_data = self.configuration[section][key].split(",")
        data_list = [data.strip() for data in raw_data]
        return data_list

    def get_path(self):
        """ Acquisisce la path avendo cura di rimuovere il trailing "/" alla fine se presente """
        path = self.configuration["disk"]["mount_point"].rstrip("/")
        return path

    def get(self, section, key):
        """ Acquisisce un valore dal file di configurazione, il valore è sempre una stringa """
        return self.configuration[section][key]

    def exists(self, section, key):
        """ Determina se il campo degli argomenti è valorizzato o no. True = valorizzato False = non valorizzato """
        try:
            x = self.configuration[section][key]
            return True
        except KeyError:
            return False


class MountUsb:

    log = logging.getLogger('mount')
    null_handler = logging.NullHandler()
    log.addHandler(null_handler)

    def __init__(self):

        # carico file di configurazione
        self.configuration = Configurator(os.path.join(BASE_DIR, "backup/mover.cfg"))

        self.log.info("=======  COPIA BACKUP STORICO SU DISCO ESTERNO  =======  \n")

        # definisco il punto di mount
        self.mount_point = self.configuration.get_path()

        # controllo eventuali mount appesi
        self.check_hanging_mount()

    def check_hanging_mount(self):
        """ Effettua la verifica di avevntuali mount appesi e nel caso li elimina.
            Se in modalità debug in caso di errore stamperà l' output di errore nel file.log """
        self.log.debug("In esecuzione la funzione 'check_hanging_mount'")
        command = Popen("/bin/mount", shell=True, stdout=PIPE)
        self.log.debug(
            "Eseguo il parsing dell' output del comando '/bin/mount'"
        )
        for line in command.stdout:
            line_cod = line.decode("utf-8")
            if self.mount_point in line_cod:
                self.log.debug(line_cod)
                self.log.warning(
                    "Trovato mount precedente appeso in '{}'. Provvedo a rimuoverlo"
                        .format(self.mount_point)
                )
                self.log.debug(
                    "Eseguo call '/bin/mount -l {}'"
                        .format(self.mount_point)
                )
                u_mount = call("/bin/umount -l {}".format(self.mount_point), shell=True)
                if u_mount != 0:
                    self.log.error("Non è stato possibile rimuovere il mount appeso")
                    if self.configuration.get("log", "level") == "debug":
                        self.log.debug("Stampo output del comando '/bin/mount -l {}' \n"
                                       .format(self.mount_point)
                                       )
                        u_mount = Popen(
                            "/bin/umount -l {}"
                            .format(self.mount_point),
                            shell=True,
                            stdout=PIPE,
                            stderr=STDOUT
                        )
                        for output in u_mount.stdout and u_mount.stderr:
                            output_cod = output.decode("utf-8")
                            self.log.debug("{}".format(output_cod))
                else:
                    self.log.info("Rimozione mount appeso avvenuto con successo. Effettuo di nuovo la verifica")
                    command = Popen("/bin/mount", shell=True, stdout=PIPE)
                    self.log.debug("Eseguo Popen su '/bin/mount'")
                    for line in command.stdout:
                        line_cod = line.decode("utf-8")
                        if self.mount_point in line_cod:
                            self.log.error(
                                "Trovato nuovamente mount precedente appeso in '{}'. Esecuzione interrotta"
                                    .format(self.mount_point)
                            )
                            sys.exit()
                        else:
                            self.log.info("Nessun mount appeso trovato")
                            return

    def disk_is_present(self):
        """ controlla se uno dei dischi è presente sulla basse degli uuid inseriti nel file .conf"""
        self.log.debug("In esecuzione la funzione 'disk_is_present'")
        is_present = None
        self.log.debug("Eseguo Popen di '/sbin/blkid'")
        command = Popen("/sbin/blkid", stdout=PIPE, shell=True)
        for line in command.stdout:
            line_cod = line.decode("utf-8")
            for uuid in self.configuration.get_as_list("disk", "uuid"):
                if uuid in line_cod:
                    self.log.info("Rilevato disco con UUID '{}'".format(uuid))
                    self.uuid = uuid
                    self.log.debug("Valore variabile 'self.uuid': {}".format(self.uuid))
                    is_present = True
                    self.log.debug("disk_is_present = {} \n".format(is_present))
                    return is_present
                else:
                    is_present = False
                    continue
        self.log.debug("disk_is_present = {} \n".format(is_present))
        return is_present

    def is_mounted(self, uuid):
        """ Controlla se il disco è montato:
            True = montato
            False = non montato
            """
        self.log.debug("In esecuzione la funzione 'is_mounted'")
        is_mount = os.path.ismount(self.mount_point)
        if not is_mount:
            self.log.info("il disco non è montato. Provvedo a montarlo in '{}'".format(self.mount_point))
            mount = call("/bin/mount -U {} {}".format(uuid, self.mount_point), shell=True)
            if mount != 0:
                self.log.error("Non è stato possibile montare il disco")
                if self.configuration.get("log", "level") == "debug":
                    self.log.debug("Stampo output del comando '/bin/mount -U {} {} \n".format(uuid, self.mount_point))
                    command = Popen(
                        "/bin/mount -U {} {}"
                        .format(uuid, self.mount_point),
                        shell=True,
                        stdout=PIPE,
                        stderr=STDOUT
                    )
                    for line in command.stdout:
                        line_cod = line.decode("utf-8")
                        self.log.debug("{}".format(line_cod))
            else:
                is_mount = os.path.ismount(self.mount_point)
        self.log.debug("Valore funzione 'is_mounted': {} \n".format(is_mount))
        return is_mount

    def handle_wrong_mount_point(self):
        """ nel caso in cui il disco sia montato nel punto sbagliato lo smonta e lo monta nel punto corretto """
        self.log.debug("Funzione 'handle_wrong_mount_point' in esecuzione")
        self.log.info("Il disco presente è {}".format(self.uuid))
        right_spot = None
        command = Popen("/sbin/blkid", shell=True, stdout=PIPE)
        for line in command.stdout:
            line_cod = line.decode("utf-8")
            if self.uuid in line_cod:
                disk_id = line_cod.split()[0].strip(":")
                self.log.debug("Identifico il nome della partizione")
                self.log.debug("Il disco è {}".format(disk_id))
                command_2 = Popen(
                    "/bin/mount", shell=True, stdout=PIPE
                )
                for line in command_2.stdout:
                    line_cod = line.decode("utf-8")
                    if disk_id in line_cod:
                        base = line_cod.split()
                        index = base.index("on")
                        new_index = index + 1
                        wrong_mount_point = base[new_index]
                        self.log.debug("Valore della variabile 'wrong_mount_point' : {}".format(wrong_mount_point))
                        if wrong_mount_point != self.mount_point:
                            self.log.warning(
                                "il mount point corretto è '{}' ma il disco '{}' è montato in '{}'"
                                .format(self.mount_point, self.uuid,wrong_mount_point)
                                        )
                            right_spot = True
                            self.log.info("Smonto il disco da {}".format(wrong_mount_point))
                            umount = call("/bin/umount -l {}".format(wrong_mount_point), shell=True)
                            if umount != 0:
                                self.log.error("Non è stato possibile smontare il disco. Esecuzione interretta")
                                if self.configuration.get("log", "level") == "debug":
                                    umount = Popen("/bin/umount -l {}"
                                                   .format(wrong_mount_point),
                                                   shell=True,
                                                   stdout=PIPE,
                                                   stderr=STDOUT
                                                   )
                                    for output in umount.stdout:
                                        output_cod = output.decode("utf-8")
                                        self.log.debug(
                                            "Stampo output del comando '/bin/umount -l {} \n".format(wrong_mount_point)
                                        )
                                        self.log.debug("{}".format(output_cod))
                                else:
                                    self.log.debug("Chiudo Script")
                                    return
                            else:
                                check = self.is_mounted(self.uuid)
                                self.log.debug("Fine esecuzione 'handle_wrong_mount_point'")
                                if check:
                                    self.log.info(
                                        "il disco con UUID '{}' è montato correttamente in '{}'"
                                        .format(self.uuid, self.mount_point)
                                    )
                                    right_spot = True
                        else:
                            self.log.error("Il disco è montato nel punto corretto. Errore sconosciuto")
                            return sys.exit()
                    else:
                        continue
        self.log.debug("Valore di 'handle_wrong_mount_point' : {}".format(right_spot))
        return right_spot

    def can_exec_backup(self):
        """ Verifica se il disco è presente e montato. Se ritorna True il backup si può eseguire """
        self.log.debug("Funzione 'can_exec_backup' in esecuzione")
        if self.disk_is_present() and self.is_mounted(self.uuid):
            start = True
            self.log.info(
                "il disco con UUID '{}' è montato correttamente in '{}'\n"
                .format(self.uuid, self.mount_point)
            )
        elif not self.disk_is_present():
            self.log.warning("Non è stato rilevato alcun disco")
            start = False
        else:
            self.log.warning("Non è stato possibile montare il disco a causa di un errore. Provo a risolvere\n")
            if self.handle_wrong_mount_point():
                start = True
            else:
                start = False
        self.log.debug("Valore exec_backup = {}".format(start))
        return start

    def unmount(self):
        self.log.debug("Funzione 'unmount' in esecuzione")
        self.log.info("Smonto il disco da {}\n".format(self.mount_point))
        umount = call("/bin/umount -l {}".format(self.mount_point), shell=True)
        if umount == 0:
            self.log.info("Disco smontato correttamente")
            return
        else:
            self.log.warning("Attenzione! il disco non è stato smontato")


class BackupMover:

    log = logging.getLogger('mover')
    null_handler = logging.NullHandler()
    log.addHandler(null_handler)

    def __init__(self):
        self.configuration = Configurator(CONF_PATH)
        self.srv_path_all = [root for root, dirs, _, in os.walk(SOURCE_DIR) if "month" in dirs]
        _, self.used_space, self.free_space = disk_usage_gb(self.configuration.get("disk", "mount_point"))

    def check_threshold(self):
        """ Controlla lo spazio disponibile in base alla soglia critica """
        threshold = int(self.configuration.get("disk", "threshold"))
        if self.free_space < threshold:
            self.log.warning("Lo spazio disponibile è al di sotto della soglia critica")
            self.log.warning("Soglia impostata a '{} GB'".format(threshold))
            return False
        return True

    def check_month_folder(self):
        """ Esclude i server che non hanno file dentro la cartella month """
        empty_path = []
        for srv in self.srv_path_all:
            path = os.path.join(srv, "month/*")
            file_list = glob.glob(path)
            if not file_list:
                empty_path.append(srv)
        result = [path for path in self.srv_path_all if path not in empty_path]
        return result

    @staticmethod
    def get_file_list(path):
        """ Ritona la lista dei file dentro la cartella month """
        f_path = os.path.join(path, "month/*")
        f_list = glob.glob(f_path)
        return f_list

    @staticmethod
    def get_oldest_file(f_list):
        """ Ritorna il file più vecchio in una lista di file """
        oldest_file = min(f_list, key=os.path.getmtime)
        return oldest_file

    @staticmethod
    def get_size(file):
        """ Ritorna la dimensione in GB del file"""
        metadata = os.stat(file)
        file_size = round(metadata.st_size / 1024 / 1024 / 1024, 2)
        return file_size

    @staticmethod
    def get_new_name(file_path):
        """ genera il nuvo nome del file """
        file = os.path.basename(file_path)
        metadata = os.stat(file_path)
        file_name = file.split(".")[0]
        file_timespamp = metadata.st_mtime
        file_date = datetime.fromtimestamp(file_timespamp)
        file_day = str(file_date.day).zfill(2)
        file_month = str(file_date.month).zfill(2)
        file_year = file_date.year
        new_file_name = "{}_{}_{}_{}.gz".format(
            file_name, file_day, file_month, file_year   # genero nome con cui rinominerò il file (nomeimmagine_giorno_mese_anno.gz)
        )
        return new_file_name

    def mv(self, source, dest):
        """ Effettua la copia e ritorna True o False """
        if not os.path.exists(os.path.dirname(dest)):  # se la cartella nel disco esterno non è presente la creo
            os.makedirs(os.path.dirname(dest))
        log.info("Inizio copia di '{}'".format(os.path.basename(source)))
        mv = call("/usr/bin/mv {} {}".format(source, dest), shell=True)
        if mv == 0:
            self.log.info("Copia di '{}' effettuata con successo".format(os.path.basename(source)))
            return True
        else:
            self.log.error(
                "Qualcosa è andato storto nello spostamento di '{}'"
                .format(os.path.basename(source))
            )
            mv = Popen(
                "/usr/bin/mv {} {}".format(
                    source, dest
                ), shell=True, stdout=PIPE, stderr=STDOUT, universal_newlines=True
            )
            self.log.error("Output Errore:\n"
                           "{}".format(mv.stdout.readlines())
                           )
            return False


if __name__ == '__main__':
    # creo logger
    log = logger()
    # instanzio classe MountUsb
    mounter = MountUsb()
    # # Istanzio Configuratore
    configuration = Configurator(CONF_PATH)
    # # genero path di log
    log_path = os.path.join(LOG_DIR, configuration.get("log", "name"))
    # se il mounter rilascia True allora posso iniziare il processo di copia
    if mounter.can_exec_backup():
        mover = BackupMover()
        # Per prima cosa Controllo lo spazio libero sul disco
        space_check = mover.check_threshold()
        # Primo Loop ( fino a che siamo nella soglia)
        while space_check:
            srv_path = mover.check_month_folder()   # lista delle path con almeno un file dentro month
            # Secondo loop ( Fino a che c'è almeno ancora un file da copiare )
            while srv_path:
                # Terzo Loop - Per ogni server tiro giu la lista dei file e seleziono il più vecchio
                for srv in srv_path:
                    # nome server
                    srv_name = os.path.basename(os.path.normpath(srv))

                    file_list = mover.get_file_list(srv)
                    oldest_file_path = mover.get_oldest_file(file_list)  # estrapolo il più vecchio # PATH SORGENTE (compreso il file
                    oldest_file_size = mover.get_size(oldest_file_path)
                    n_file_name = mover.get_new_name(oldest_file_path)
                    dest_dir = os.path.join(configuration.get("disk", "mount_point"), "{}".format(srv_name))
                    destination_path = os.path.join(dest_dir, n_file_name)  # PATH DESTINAZIONE (compreso il file )
                    if oldest_file_size < mover.free_space:
                        if mover.mv(oldest_file_path, destination_path):
                            _, _, free_space = disk_usage_gb(configuration.get("disk", "mount_point"))
                            log.info("Spazio rimasto: '{} GB'\n".format(
                                round(free_space, 2)
                            ))
                            space_check = mover.check_month_folder()
                            srv_path = mover.check_month_folder()

                    else:
                        log.warning("Non c'è abbastanza spazio per copiare '{}'".format(os.path.basename(oldest_file_path)))
                        space_check = mover.check_month_folder()
                        srv_path = mover.check_month_folder()

            # Secondo Loop stop - Nessun file rimasto
            log.info(
                "Tutte le cartelle 'month' sono vuote"
            )
            _, used_space, free_space = disk_usage_gb(configuration.get("disk", "mount_point"))
            mounter.unmount()
            send_mail(
                subject="[SUCCESSO] Backup Storico",
                content="Copia backup storici su disco esterno avvenuta con successo!\n"
                        "Spazio Libero rimasto: {} GB\n"
                        "Spazio Occupato: {} GB\n"
                        "Leggere il log per maggiori informazioni".format(
                         round(free_space, 2), round(used_space, 2),
                        ),
                attach_name=log_path
            )
            sys.exit()

        # Primo loop stop - spazio al di sotto del livello critico
        _, used, free = disk_usage_gb(configuration.get("disk", "mount_point"))
        mounter.unmount()  # smonto disco
        send_mail(
            subject="[ATTENZIONE] Backup Storico",
            content="Lo spazio disponibile sul disco è al di sotto del livello critico!\n"
                    "Spazio Libero rimasto: {} GB\n"
                    "Spazio Occupato: {} GB\n"
                    "Leggere il log per maggiori informazioni".format(
                     round(free, 2), round(used, 2),
                    ),
            attach_name=log_path
        )

    # Mount non eseguito
    else:
        log.error("La copia dei backup storici non è stata eseguita")
        send_mail(
            subject="[ERRORE] Backup Storico",
            content="La copia dei backup storici non è stata eseguita, vedi log per maggiori informazioni",
            attach_name=log_path
        )
