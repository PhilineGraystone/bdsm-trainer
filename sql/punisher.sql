-- MySQL dump 10.17  Distrib 10.3.22-MariaDB, for debian-linux-gnueabihf (armv8l)
--
-- Host: localhost    Database: punisher
-- ------------------------------------------------------
-- Server version	10.3.22-MariaDB-0+deb10u1

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `current_device`
--

DROP TABLE IF EXISTS `current_device`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `current_device` (
  `cd_id` int(11) NOT NULL AUTO_INCREMENT,
  `cd_devid` int(11) NOT NULL,
  `cd_name` varchar(120) NOT NULL,
  PRIMARY KEY (`cd_id`),
  UNIQUE KEY `cd_devid` (`cd_devid`)
) ENGINE=MEMORY DEFAULT CHARSET=utf8;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `current_device`
--

LOCK TABLES `current_device` WRITE;
/*!40000 ALTER TABLE `current_device` DISABLE KEYS */;
/*!40000 ALTER TABLE `current_device` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `current_slave`
--

DROP TABLE IF EXISTS `current_slave`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `current_slave` (
  `cur_id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `cur_slaveid` int(10) unsigned NOT NULL,
  `cur_name` varchar(255) NOT NULL,
  `cur_program` varchar(60) NOT NULL,
  PRIMARY KEY (`cur_id`),
  UNIQUE KEY `cur_slaveid` (`cur_slaveid`)
) ENGINE=MEMORY DEFAULT CHARSET=utf8;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `current_slave`
--

LOCK TABLES `current_slave` WRITE;
/*!40000 ALTER TABLE `current_slave` DISABLE KEYS */;
/*!40000 ALTER TABLE `current_slave` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `devices`
--

DROP TABLE IF EXISTS `devices`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `devices` (
  `dev_id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `dev_name` varchar(60) NOT NULL,
  `dev_address` varchar(60) NOT NULL,
  `dev_protocol` enum('433','MQTT') NOT NULL DEFAULT 'MQTT',
  PRIMARY KEY (`dev_id`),
  UNIQUE KEY `dev_name` (`dev_name`)
) ENGINE=Aria AUTO_INCREMENT=4 DEFAULT CHARSET=utf8 PAGE_CHECKSUM=1;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `devices`
--

LOCK TABLES `devices` WRITE;
/*!40000 ALTER TABLE `devices` DISABLE KEYS */;
INSERT INTO `devices` VALUES (1,'torturedevice01','172.16.1.204','MQTT'),(2,'torturedevice02','172.16.1.205','MQTT'),(3,'torturedevice03','9803','433');
/*!40000 ALTER TABLE `devices` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `devtoslave`
--

DROP TABLE IF EXISTS `devtoslave`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `devtoslave` (
  `dts_id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `dts_deviceid` int(10) unsigned NOT NULL,
  `dts_slaveid` int(10) unsigned NOT NULL,
  PRIMARY KEY (`dts_id`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `devtoslave`
--

LOCK TABLES `devtoslave` WRITE;
/*!40000 ALTER TABLE `devtoslave` DISABLE KEYS */;
INSERT INTO `devtoslave` VALUES (3,1,1),(4,2,1),(5,3,1);
/*!40000 ALTER TABLE `devtoslave` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `program`
--

DROP TABLE IF EXISTS `program`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `program` (
  `pro_id` int(11) NOT NULL AUTO_INCREMENT,
  `pro_name` varchar(120) NOT NULL,
  `pro_functions` varchar(255) NOT NULL,
  PRIMARY KEY (`pro_id`),
  UNIQUE KEY `pro_name` (`pro_name`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `program`
--

LOCK TABLES `program` WRITE;
/*!40000 ALTER TABLE `program` DISABLE KEYS */;
INSERT INTO `program` VALUES (1,'Painplay','tens|random'),(2,'Blowjob','blowjob|50');
/*!40000 ALTER TABLE `program` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `slaves`
--

DROP TABLE IF EXISTS `slaves`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `slaves` (
  `slave_id` int(11) NOT NULL AUTO_INCREMENT,
  `slave_rfid` varchar(255) NOT NULL,
  `slave_name` varchar(255) NOT NULL,
  `slave_collar` varchar(255) NOT NULL,
  `slave_program` int(11) unsigned NOT NULL,
  PRIMARY KEY (`slave_id`),
  UNIQUE KEY `slave_rfid` (`slave_rfid`)
) ENGINE=Aria AUTO_INCREMENT=3 DEFAULT CHARSET=utf8 PAGE_CHECKSUM=1;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `slaves`
--

LOCK TABLES `slaves` WRITE;
/*!40000 ALTER TABLE `slaves` DISABLE KEYS */;
INSERT INTO `slaves` VALUES (1,'<RFID>','<SLAVE NAME>','<COLLARID>',1);
/*!40000 ALTER TABLE `slaves` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `torfunctions`
--

DROP TABLE IF EXISTS `torfunctions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `torfunctions` (
  `tf_id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `tf_devid` int(10) unsigned NOT NULL,
  `tf_name` varchar(120) NOT NULL,
  `tf_pic` varchar(80) NOT NULL,
  `tf_call` varchar(120) NOT NULL,
  `tf_args` enum('seconds','enable','disable','random') NOT NULL DEFAULT 'seconds',
  PRIMARY KEY (`tf_id`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `torfunctions`
--

LOCK TABLES `torfunctions` WRITE;
/*!40000 ALTER TABLE `torfunctions` DISABLE KEYS */;
INSERT INTO `torfunctions` VALUES (1,1,'tens','tens.png','tortureon','seconds'),(2,2,'tens','tens.png','tortureon','seconds'),(3,3,'blowjob','blow.png','433','enable');
/*!40000 ALTER TABLE `torfunctions` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2020-05-16 22:02:02
