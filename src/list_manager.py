# Compare the elements of all lists to check for duplicates
# Then ask user to choose which list they want it to remain on
import functions as pf

if __name__ == "__main__":

    #  Remove blank lines from email lists
    pf.rm_blanks("white")
    pf.rm_blanks("black")
    pf.rm_blanks("vendor")
    pf.rm_blanks("head")

    #  Open email lists and read into memory
    black = pf.open_read("black")
    vendor = pf.open_read("vendor")
    white = pf.open_read("white")
    head = pf.open_read("head")

    #  Make list of common emails in each list against each other
    black_vendor = [email for email in black if email in vendor if email != "\n"]
    black_white = [email for email in black if email in white if email != "\n"]
    white_vendor = [email for email in white if email in vendor if email != "\n"]
    head_black = [email for email in head if email in black if email != "\n"]
    head_white = [email for email in head if email in white if email != "\n"]
    head_vendor = [email for email in head if email in vendor if email != "\n"]


    #  Disposition each item
    for item in black_white:
        response = ""
        while response not in ("1","2"):
            response = input(f"{item} is in both blacklist and whitelist.  Where does it belong?\n1. Blacklist\n2. Whitelist\n")
            if response == "1":
                pf.remove_entry(item, "white")
            elif response == "2":
                pf.remove_entry(item, "black")

    for item in black_vendor:
        response = ""
        while response not in ("1","2"):
            response = input(f"{item} is in both blacklist and vendor list.  Where does it belong?\n1. Blacklist\n2. Vendor List\n")
            if response == "1":
                pf.remove_entry(item, "vendor")
            elif response == "2":
                pf.remove_entry(item, "black")

    for item in white_vendor:
        response = ""
        while response not in ("1","2"):
            response = input(f"{item} is in both vendor list and whitelist.  Where does it belong?\n1. Vendor List\n2. Whitelist\n")
            if response == "1":
                pf.remove_entry(item, "white")
            elif response == "2":
                pf.remove_entry(item, "vendor")

    for item in head_black:
        response = ""
        while response not in ("1","2"):
            response = input(f"{item} is in both head list and blacklist.  Where does it belong?\n1. Head List\n2. Blacklist\n")
            if response == "1":
                pf.remove_entry(item, "black")
            elif response == "2":
                pf.remove_entry(item, "head")

    for item in head_white:
        response = ""
        while response not in ("1","2"):
            response = input(f"{item} is in both head list and whitelist.  Where does it belong?\n1. Head List\n2. Whitelist\n")
            if response == "1":
                pf.remove_entry(item, "white")
            elif response == "2":
                pf.remove_entry(item, "head")

    for item in head_vendor:
        response = ""
        while response not in ("1","2"):
            response = input(f"{item} is in both head list and vendor list.  Where does it belong?\n1. Head List\n2. Vendor List\n")
            if response == "1":
                pf.remove_entry(item, "vendor")
            elif response == "2":
                pf.remove_entry(item, "head")