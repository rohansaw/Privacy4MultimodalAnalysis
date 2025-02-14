import React, { useEffect } from 'react';
import { CssBaseline } from "@mui/material";
import { Navigate, Route, Routes } from "react-router";
import PageLayout from "./layout/PageLayout";
import VideosPage from "./pages/VideosPage";
import RunsPage from './pages/RunsPage';
import PresetsPage from './pages/PresetsPage';
import Command from "./state/actions/command";
import { useDispatch } from "react-redux";
import Paths from "./paths";
import WorkersPage from "./pages/WorkersPage";
import VideosMaskingPage from "./pages/VideosMaskingPage"
import LandingPage from "./pages/LandingPage";
import AboutPage from "./pages/AboutPage";

const App = () => {
    const dispatch = useDispatch();

    useEffect(() => {
        dispatch(Command.Video.fetchVideoList({}));
        dispatch(Command.Job.fetchJobList({}));
        dispatch(Command.Worker.fetchWorkerList({}));
        dispatch(Command.Preset.fetchPresetList({}));
    }, []);

    return (<>
        <CssBaseline />
        <Routes>
            <Route path={'/home'} element={<LandingPage />} />
            <Route path={'/'} element={<PageLayout />}>
                <Route path={Paths.videos} element={<VideosPage />} />
                <Route path={Paths.videoDetails} element={<VideosPage />} />
                <Route path={Paths.videoRunMasking} element={<VideosMaskingPage />} />
                <Route path={Paths.resultVideoDetails} element={<VideosPage />} />
                <Route path={Paths.runs} element={<RunsPage />} />
                <Route path={Paths.presets} element={<PresetsPage />} />
                <Route path={Paths.workers} element={<WorkersPage />} />
                <Route path={Paths.about} element={<AboutPage />} />
                <Route index={true} element={<Navigate to={Paths.videos} replace={true} />} />
            </Route>
        </Routes>
    </>);
};

export default App;
