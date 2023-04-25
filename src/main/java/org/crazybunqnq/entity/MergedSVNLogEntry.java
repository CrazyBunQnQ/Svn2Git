package org.crazybunqnq.entity;

import org.tmatesoft.svn.core.SVNLogEntry;
import org.tmatesoft.svn.core.SVNLogEntryPath;

import java.util.Date;
import java.util.LinkedHashMap;
import java.util.Map;

public class MergedSVNLogEntry {
    private long revision;
    private String author;
    private Date date;
    private String message;
    private Map<String, SVNLogEntryPath> changedPaths;

    public MergedSVNLogEntry(SVNLogEntry logEntry) {
        this.revision = logEntry.getRevision();
        this.author = logEntry.getAuthor();
        this.date = logEntry.getDate();
        this.message = logEntry.getMessage();
        this.changedPaths = new LinkedHashMap<>(logEntry.getChangedPaths());
    }

    public long getRevision() {
        return revision;
    }

    public void setRevision(long revision) {
        this.revision = revision;
    }

    public String getAuthor() {
        return author;
    }

    public Date getDate() {
        return date;
    }

    public void setDate(Date date) {
        this.date = date;
    }

    public String getMessage() {
        return message;
    }

    public void setMessage(String message) {
        this.message = message;
    }

    public Map<String, SVNLogEntryPath> getChangedPaths() {
        return changedPaths;
    }
}

