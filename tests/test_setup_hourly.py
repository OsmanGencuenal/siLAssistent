import unittest
from datetime import datetime
from unittest.mock import Mock,patch
from source.stand_management.setup_updates import SetupUpdates
from source.core.config import Config

class SetupHourlyTests(unittest.TestCase):
    @classmethod
    def test_check_once_per_hour_and_again_at_next_full_hour(cls):
        parent=Mock();parent.isVisible.return_value=True;parent._git={}
        timer=Mock()
        with patch("shiboken6.isValid",return_value=True),patch.object(SetupUpdates,"_automatic_check",False,create=True),patch.object(SetupUpdates,"_hourly_context",(parent,"git"),create=True),patch.object(SetupUpdates,"_hourly_timer",timer,create=True),patch.object(SetupUpdates,"_hourly_checked",{},create=True),patch.object(SetupUpdates,"_active",False,create=True),patch.object(Config,"state",return_value={"GitLocalRepoPath":"repo"}),patch.object(SetupUpdates,"start") as start:
            SetupUpdates.hourly_tick(datetime(2026,11,11,12,15))
            start.assert_called_once_with(parent,"git",offer=True)
            timer.start.assert_called_with(45*60*1000)
            SetupUpdates.hourly_tick(datetime(2026,11,11,12,50))
            assert start.call_count==1
            SetupUpdates.hourly_tick(datetime(2026,11,11,13,0))
            assert start.call_count==2

    @classmethod
    def test_busy_action_defers_check_without_consuming_hour(cls):
        parent=Mock();parent.isVisible.return_value=True;parent._git={}
        timer=Mock();checked={}
        with patch("shiboken6.isValid",return_value=True),patch.object(SetupUpdates,"_automatic_check",False,create=True),patch.object(SetupUpdates,"_hourly_context",(parent,"drive"),create=True),patch.object(SetupUpdates,"_hourly_timer",timer,create=True),patch.object(SetupUpdates,"_hourly_checked",checked,create=True),patch.object(SetupUpdates,"_active",True,create=True),patch.object(SetupUpdates,"start") as start:
            SetupUpdates.hourly_tick(datetime(2026,11,11,13,0))
            start.assert_not_called()
            timer.start.assert_called_with(15000)
            assert not checked

    @classmethod
    def test_click_offers_only_selected_mode_even_within_same_hour(cls):
        parent=Mock();parent.isVisible.return_value=True;parent._git={}
        timer=Mock()
        now=datetime(2026,11,11,13,0)
        with patch("shiboken6.isValid",return_value=True),patch.object(SetupUpdates,"_automatic_check",False,create=True),patch.object(SetupUpdates,"_hourly_context",(parent,"drive"),create=True),patch.object(SetupUpdates,"_hourly_timer",timer,create=True),patch.object(SetupUpdates,"_hourly_checked",{"drive":now.strftime("%Y-%m-%d %H %z")},create=True),patch.object(SetupUpdates,"_active",False,create=True),patch.object(Config,"state",return_value={"DriveSetupLocalPath":"local"}),patch.object(SetupUpdates,"start") as start:
            SetupUpdates.hourly_tick(now,offer=True)
            start.assert_called_once_with(parent,"drive",offer=True)

    @classmethod
    def test_background_result_never_shows_offer_even_for_new_counter(cls):
        process=Mock();process.is_alive.return_value=False
        receiver=Mock();receiver.poll.return_value=True
        receiver.recv.return_value={"error":None,"result":{"available":True,"counter":42,"source":"LW"}}
        state={"process":process,"receiver":receiver,"timer":Mock(),"parent":object(),"mode":"git","operation":"check","offer":False,"result":None}
        with patch.object(SetupUpdates,"_active",True,create=True),patch.object(SetupUpdates,"confirm") as confirm:
            SetupUpdates.poll(state)
            confirm.assert_not_called()
